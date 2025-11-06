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

        try:
            # Connect over ssh
            self.ssh_client.connect(**self.com_info)
            sftp = self.ssh_client.open_sftp()

            # Create list to hold new filenames
            new_fnames = []

            # Get the file names in the local directory
            local_files = os.listdir(local_dir)

            # Get the file names in the remote directory
            try:
                remote_files = sftp.listdir(remote_dir)
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
                    sftp.get(
                        remote_dir + fname,
                        local_dir + fname,
                        preserve_mtime=True
                    )

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

        return new_fnames, err

    # Get status ==============================================================
    def pull_status(self, filenmae='/home/scan/OpenSO2/Station/status.txt'):
        """Pull the station status."""
        # Make sure the Station folder exists
        if not os.path.exists('Station'):
            os.makedirs('Station')

        try:
            # Connect over ssh
            self.ssh_client.connect(**self.com_info)
            sftp = self.ssh_client.open_sftp()

            # Get the status file
            sftp.get(
                filenmae,
                f'Station/{self.name}_status.txt',
                preserve_mtime=True
            )

            # Read the status file
            with open(f'Station/{self.name}_status.txt', 'r') as r:
                time, status = r.readline().strip().split(' - ')

            # Successful read
            err = [False, '']

        # If connection fails, report
        except paramiko.SSHException as e:
            time, status = '-', 'N/C'
            err = [True, e]

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
        # Get the date to find the correct log file
        if sdate is None:
            sdate = dt.now().date()

        # Make sure the Station folder exists
        if not os.path.exists(f'{local_dir}/{sdate}/{self.name}'):
            os.makedirs(f'{local_dir}/{sdate}/{self.name}')

        try:
            # Connect over ssh
            self.ssh_client.connect(**self.com_info)
            sftp = self.ssh_client.open_sftp()

            # Get the status file
            try:
                sftp.get(
                    f'{remote_dir}/{sdate}/{sdate}.log',
                    f'{local_dir}/{sdate}/{self.name}/{sdate}.log',
                    preserve_mtime=True
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

        return fname, err
