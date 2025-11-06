"""Control communication between the home computer and the scanning station."""

import os
import logging
from datetime import datetime as dt
import paramiko

logger = logging.getLogger(__name__)

class Station():

    def __init__(self, name, com_info, loc_info, sync_flag=True,
                 filter_spectra_flag=True):
        """Initialise."""

        self.name = name
        self.com_info = com_info
        self.loc_info = loc_info
        self.sync_flag = sync_flag
        self.filter_spectra_flag = filter_spectra_flag

        self.ssh_client = paramiko.SSHClient()
        self.ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        self.connected = False

    def connect(self):
        logger.info(f'Connecting to scanner {self.name}')
        self.ssh_client.connect(**self.com_info)
        self.sftp = self.ssh_client.open_sftp()
        self.connected = True


    # Sync folder =============================================================
    def sync(self, local_dir, remote_dir):
        """Sync a local folder with a remote one.

        Parameters
        ----------
        local_dir : str
            File path to the local folder
        remote_dir : str
            File path to the remote folder

        Returns
        -------
        list
            List of synced file name strings
        tuple
            Error flag and message as [flag, 'msg']
        """

        if not self.connected:
            self.connect()

        logger.info(f'Fetching files from {self.name}')

        try:

            # Create list to hold new filenames
            new_fnames = []

            # Get the file names in the local directory
            local_files = os.listdir(local_dir)

            # Get the file names in the remote directory
            try:
                remote_files = self.sftp.listdir(remote_dir)
            except FileNotFoundError:
                logger.info('No files found')
                return [], [False, '']

            # FInd the files to sync
            files_to_sync = [
                f for f in remote_files if f not in local_files
            ]

            logger.info(f'Found {len(files_to_sync)} files to sync')

            # Iterate through and download
            for fname in files_to_sync:

                # Copy the file across
                try:
                    self.sftp.get(remote_dir + fname, local_dir + fname)

                    # Add file list
                    new_fnames.append(fname)
                except OSError:
                    logger.warning(f'Error syncing {fname}')

            # Set error message as false
            err = [False, '']

        # Handle the error is the connection is refused
        except (paramiko.SSHException, FileNotFoundError) as e:
            logger.info(
                f'Error with station {self.name} communication',
                exc_info=True
            )
            new_fnames = []
            err = [True, e]
            self.sftp.close()
            self.connected = False

        return new_fnames, err

    # Get status ==============================================================
    def pull_status(self, filename='/home/scan/OpenSO2/Station/status.txt'):
        """Pull the station status."""
        logger.info(f'Fetching {self.name} status')

        if not self.connected:
            self.connect()
        # Make sure the Station folder exists
        if not os.path.exists('Station'):
            os.makedirs('Station')

        try:

            # Get the status file
            self.sftp.get(filename, f'Station/{self.name}_status.txt')

            # Read the status file
            with open(f'Station/{self.name}_status.txt', 'r') as r:
                time, status = r.readline().strip().split(' - ')

            # Successful read
            err = [False, '']

        # If connection fails, report
        except paramiko.SSHException as e:
            time, status = '-', 'N/C'
            err = [True, e]
            self.sftp.close()
            self.connected = False

        return time, status, err

    # Pull log ================================================================
    def pull_log(self, local_dir='Results', remote_dir='/home/scan/Results',
                 sdate=None):
        """Pull the log file from the station for analysis.

        NOTE THIS ASSUMES THE DATE ON THE PI IS CORRECT TO PULL THE CORRECT LOG
        FILE

        Parameters
        ----------
        sdate : datetime.date object or None, optional
            The date to sync the log for. If None, then today is used.

        Returns
        -------
        last_log : str
            The last log entry in the log file
        err : tuple
            Consists of the error flag (True is an error occured) and the error
            message
        """
        logger.info(f'Fetching {self.name} logs')

        if not self.connected:
            self.connect()

        # Get the date to find the correct log file
        if sdate is None:
            sdate = dt.now().date()

        # Make sure the Station folder exists
        if not os.path.exists(f'{local_dir}/{sdate}/{self.name}'):
            os.makedirs(f'{local_dir}/{sdate}/{self.name}')

        try:

            # Get the status file
            try:
                self.sftp.get(
                    f'{remote_dir}/{sdate}/{sdate}.log',
                    f'{local_dir}/{sdate}/{self.name}/{sdate}.log'
                )
                fname = f'{local_dir}/{sdate}/{self.name}/{sdate}.log'
            except FileNotFoundError:
                fname = None
                logger.info('No log file found')
            except OSError:
                fname = None

            # Successful read
            err = [False, '']

        # If connection fails, report
        except paramiko.SSHException as e:
            fname = None
            err = [True, e]
            self.sftp.close()
            self.connected = False

        return fname, err
