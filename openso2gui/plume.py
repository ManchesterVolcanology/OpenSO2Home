import numpy as np
from math import sin, cos, atan2, pi, asin


# =============================================================================
# haversine
# =============================================================================

def haversine(start_coords, end_coords, radius=6371000):
    """Calculate the distance and initial bearing between two points.

    Parameters
    ----------
    start_coords : tuple
        Start coordinates (lat, lon) in decimal degrees (+ve = north/east).
    end_coords : tuple
        End coordinates (lat, lon) in decimal degrees (+ve = north/east).
    radius: float, optional
        Radius of the body in meters. Default is set to the Earth radius
        (6731km).

    Returns
    -------
    distance : float
        The linear distance between the two points in meters.
    bearing : float
        The initial bearing between the two points (radians).
    """
    # Unpack the coordinates and convert to radians
    lat1, lon1 = np.radians(start_coords)
    lat2, lon2 = np.radians(end_coords)

    # Calculate the change in lat and lon
    dlat = lat2 - lat1
    dlon = lon2 - lon1

    # Calculate the square of the half chord length
    a = (sin(dlat/2))**2 + (cos(lat1) * cos(lat2) * (sin(dlon/2))**2)

    # Calculate the angular distance
    c = 2 * atan2(np.sqrt(a), np.sqrt(1-a))

    # Find distance moved
    distance = radius * c

    # Calculate the initial bearing
    bearing = atan2(sin(dlon) * cos(lat2),
                    (cos(lat1)*sin(lat2)) - (sin(lat1)*cos(lat2)*cos(dlon)))

    bearing = bearing % (2*pi)

    return distance, bearing


# =============================================================================
# Calculate end point
# =============================================================================

def calc_end_point(start_coords, distance, bearing, radius=6371000):
    """Calculate end point from a start location given a distance and bearing.

    Parameters
    ----------
    start_coords : tuple
        Starting coordinates (lat, lon) in decimal degrees (+ve = north/east).
    distance : float
        The distance moved in meters.
    bearing : float
        The bearing of travel in degrees clockwise from north.
    radius : float
        Radius of the body in meters. Default is set to the Earth radius
        (6731 km).

    Returns
    -------
    end_coords, tuple
        The final coordinates (lat, lon) in decimal degrees (+ve = north/east)
    """
    # Convert the inputs to radians
    lat, lon = np.radians(start_coords)
    theta = np.radians(bearing)

    # Calculate the angular distance moved
    ang_dist = distance / radius

    # Calculate the final latitude
    end_lat = asin(np.add((sin(lat) * cos(ang_dist)),
                          (cos(lat) * sin(ang_dist) * cos(theta))))

    # Calculate the final longitude
    end_lon = lon + atan2(sin(theta) * sin(ang_dist) * cos(lat),
                          cos(ang_dist) - (sin(lat)*sin(end_lat)))

    return np.degrees([end_lat, end_lon])