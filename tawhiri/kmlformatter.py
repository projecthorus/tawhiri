# Copyright 2022 (C) Mark Jessop
#
# This file is part of Tawhiri.
#
# Tawhiri is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Tawhiri is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Tawhiri.  If not, see <http://www.gnu.org/licenses/>.
from dateutil.parser import parse

def format_kml(data):
    """ Format a Tawhiri prediction as KML """

    # Generate LineString coordinates
    _linestring_coords = ""
    for stage in data["prediction"]:
        for point in stage["trajectory"]:
            _linestring_coords += f"{point['longitude']:.5f},{point['latitude']:.5f},{point['altitude']:.1f}\n"

    # Flight Path Descriptions
    if data['request']['profile'] == "standard_profile":
        # Standard Profile
        _linestr_description = f"Ascent rate: {data['request']['ascent_rate']:.1f}, descent rate: {data['request']['descent_rate']:.1f}, with burst at {data['request']['burst_altitude']:.1f}m."
        _flight_info = f"Flight Data for start time {data['request']['launch_datetime']}, at site: {data['request']['launch_latitude']:.4f},{data['request']['launch_longitude']:.4f}, standard flight profile."
    elif data['request']['profile'] == "float_profile":
        # Float Profile
        _linestr_description = f"Ascent rate: {data['request']['ascent_rate']:.1f}, with float at {data['request']['float_altitude']:.1f}m."
        _flight_info = f"Flight Data for start time {data['request']['launch_datetime']}, at site: {data['request']['launch_latitude']:.4f},{data['request']['launch_longitude']:.4f}, float profile, with {data['request']['float_altitude']:.1f}m float."
    elif data['request']['profile'] == "reverse_profile":
        # Reverse Profile
        _linestr_description = f"Reverse Prediction with ascent rate: {data['request']['ascent_rate']:.1f}, with start altitude at {data['request']['launch_altitude']:.1f}m."
        _flight_info = f"Reverse prediction for start time {data['request']['launch_datetime']}, at start point: {data['request']['launch_latitude']:.4f},{data['request']['launch_longitude']:.4f} at {data['request']['launch_altitude']:.4f}m altitude."
    else:
        raise InternalException("Unknown Flight Profile for KML export.")


    # Generate Placemark information
    _placemarks = ""
    if data['request']['profile'] == "standard_profile":
        # Standard Profile
        # Launch
        _point = data["prediction"][0]['trajectory'][0]
        _launch = f"""
<Placemark>
<name>Balloon Launch</name>
<description>Balloon launch at {_point['latitude']:.5f},{_point['longitude']:.5f}, at {_point['datetime']}.</description>
<Point><altitudeMode>absolute</altitudeMode><coordinates>{_point['longitude']:.5f},{_point['latitude']:.5f},{_point['altitude']:.1f}</coordinates></Point>
</Placemark>
"""
        # Burst
        _point = data["prediction"][0]['trajectory'][-1]
        _burst = f"""
<Placemark>
<name>Balloon Burst</name>
<description>Balloon burst at {_point['latitude']:.5f},{_point['longitude']:.5f}, at {_point['datetime']}.</description>
<Point><altitudeMode>absolute</altitudeMode><coordinates>{_point['longitude']:.5f},{_point['latitude']:.5f},{_point['altitude']:.1f}</coordinates></Point>
</Placemark>
"""
        # Landing
        _point = data["prediction"][-1]['trajectory'][-1]
        _landing = f"""
<Placemark>
<name>Balloon Landing</name>
<description>Balloon landing at {_point['latitude']:.5f},{_point['longitude']:.5f}, at {_point['datetime']}.</description>
<Point><altitudeMode>absolute</altitudeMode><coordinates>{_point['longitude']:.5f},{_point['latitude']:.5f},{_point['altitude']:.1f}</coordinates></Point>
</Placemark>
"""
        _placemarks += _launch + _burst + _landing


    elif data['request']['profile'] == "float_profile":
        # Float Profile
        # Launch
        _point = data["prediction"][0]['trajectory'][0]
        _launch = f"""
<Placemark>
<name>Balloon Launch</name>
<description>Balloon launch at {_point['latitude']:.5f},{_point['longitude']:.5f}, at {_point['datetime']}.</description>
<Point><altitudeMode>absolute</altitudeMode><coordinates>{_point['longitude']:.5f},{_point['latitude']:.5f},{_point['altitude']:.1f}</coordinates></Point>
</Placemark>
"""
        # Float Start
        _point = data["prediction"][0]['trajectory'][-1]
        _float = f"""
<Placemark>
<name>Float Start</name>
<description>Float start at {_point['latitude']:.5f},{_point['longitude']:.5f}, at {_point['datetime']}.</description>
<Point><altitudeMode>absolute</altitudeMode><coordinates>{_point['longitude']:.5f},{_point['latitude']:.5f},{_point['altitude']:.1f}</coordinates></Point>
</Placemark>
"""
        # Prediction End
        _point = data["prediction"][-1]['trajectory'][-1]
        _end = f"""
<Placemark>
<name>Prediction End</name>
<description>Prediction end at {_point['latitude']:.5f},{_point['longitude']:.5f}, at {_point['datetime']}.</description>
<Point><altitudeMode>absolute</altitudeMode><coordinates>{_point['longitude']:.5f},{_point['latitude']:.5f},{_point['altitude']:.1f}</coordinates></Point>
</Placemark>
"""
        _placemarks += _launch + _float + _end

    elif data['request']['profile'] == "reverse_profile":
        # Reverse Profile
        _point = data["prediction"][0]['trajectory'][0]
        _start = f"""
<Placemark>
<name>Start</name>
<description>Start at {_point['latitude']:.5f},{_point['longitude']:.5f}, at {_point['datetime']}.</description>
<Point><altitudeMode>absolute</altitudeMode><coordinates>{_point['longitude']:.5f},{_point['latitude']:.5f},{_point['altitude']:.1f}</coordinates></Point>
</Placemark>
"""
        _point = data["prediction"][-1]['trajectory'][-1]
        _launch = f"""
<Placemark>
<name>Launch Prediction</name>
<description>Launch predicted at {_point['latitude']:.5f},{_point['longitude']:.5f}, at {_point['datetime']}.</description>
<Point><altitudeMode>absolute</altitudeMode><coordinates>{_point['longitude']:.5f},{_point['latitude']:.5f},{_point['altitude']:.1f}</coordinates></Point>
</Placemark>
"""
        _placemarks += _start + _launch

    else:
        raise InternalException("Unknown Flight Profile for KML export.")

    # Generate the final KML output
    _output = f"""<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
<Document>
<name>Flight Path</name>
<description>{_flight_info}</description>
<Style id="yellowPoly">
<LineStyle>
<color>7f00ffff</color>
<width>4</width>
</LineStyle>
<PolyStyle>
<color>7f00ff00</color>
</PolyStyle>
</Style>
<Placemark>
<name>Flight path</name>
<description>{_linestr_description}</description>
<styleUrl>#yellowPoly</styleUrl>
<LineString>
<extrude>1</extrude>
<tesselate>1</tesselate>
<altitudeMode>absolute</altitudeMode>
<coordinates>
{_linestring_coords}
</coordinates>
</LineString></Placemark>
{_placemarks}
</Document></kml>
"""

    # Generate filename
    _start_datestr = data["request"]["launch_datetime"]
    _start_datetime = parse(_start_datestr)
    _start_datestr = _start_datetime.strftime("%Y%m%d-%H%M%SZ")

    _dataset_datestr = data["request"]["dataset"]
    _dataset_datetime = parse(_dataset_datestr)
    _dataset_datestr = _dataset_datetime.strftime("%Y%m%d%HZ")

    _filename = f"{_start_datestr}_{data['request']['launch_latitude']:.4f}_{data['request']['launch_longitude']:.4f}_{data['request']['profile']}_{_dataset_datestr}.kml"

    return {
        "filename": _filename, 
        "data": _output
    }