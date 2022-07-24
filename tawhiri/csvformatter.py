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

def fix_data_longitudes(data):
    """ Fix all the longitudes in the prediction trajectory to -180 to 180. """
    for stage in data["prediction"]:
        for point in stage["trajectory"]:
            if point['longitude'] > 180.0:
                point['longitude'] = point['longitude'] - 360.0

    return data

def format_csv(data):
    """ Format a Tawhiri prediction as CSV """

    # Generate CSV data.
    _output = "datetime,latitude,longitude,altitude\n"
    for stage in data["prediction"]:
        for point in stage["trajectory"]:
            _output += f"{point['datetime']},{point['latitude']:.5f},{point['longitude']:.5f},{point['altitude']:.1f}\n"

    # Generate filename
    _start_datestr = data["request"]["launch_datetime"]
    _start_datetime = parse(_start_datestr)
    _start_datestr = _start_datetime.strftime("%Y%m%d-%H%M%SZ")

    _dataset_datestr = data["request"]["dataset"]
    _dataset_datetime = parse(_dataset_datestr)
    _dataset_datestr = _dataset_datetime.strftime("%Y%m%d%HZ")

    _filename = f"{_start_datestr}_{data['request']['launch_latitude']:.4f}_{data['request']['launch_longitude']:.4f}_{data['request']['profile']}_{_dataset_datestr}.csv"

    return {
        "filename": _filename, 
        "data": _output
    }