# Copyright 2014 (C) Priyesh Patel
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

"""
Provide the HTTP API for Tawhiri.
"""

from flask import Flask, jsonify, request, g, send_file
from datetime import datetime
import time
import strict_rfc3339
from io import BytesIO

from tawhiri import solver, models
from tawhiri.dataset import Dataset as WindDataset
from tawhiri.warnings import WarningCounts
from tawhiri.csvformatter import format_csv, fix_data_longitudes
from tawhiri.kmlformatter import format_kml
from ruaumoko import Dataset as ElevationDataset
import newrelic.agent
app = Flask(__name__)

API_VERSION = 1
LATEST_DATASET_KEYWORD = "latest"
PROFILE_STANDARD = "standard_profile"
PROFILE_FLOAT = "float_profile"
PROFILE_REVERSE = "reverse_profile"
STANDARD_FORMAT = "json"


# Util functions ##############################################################
@newrelic.agent.function_trace()
def ruaumoko_ds():
    if not hasattr("ruaumoko_ds", "once"):
        ds_loc = app.config.get('ELEVATION_DATASET', ElevationDataset.default_location)
        ruaumoko_ds.once = ElevationDataset(ds_loc)

    return ruaumoko_ds.once

@newrelic.agent.function_trace()
def _rfc3339_to_timestamp(dt):
    """
    Convert from a RFC3339 timestamp to a UNIX timestamp.
    """
    return strict_rfc3339.rfc3339_to_timestamp(dt)

@newrelic.agent.function_trace()
def _timestamp_to_rfc3339(dt):
    """
    Convert from a UNIX timestamp to a RFC3339 timestamp.
    """
    return strict_rfc3339.timestamp_to_rfc3339_utcoffset(dt)


# Exceptions ##################################################################
class APIException(Exception):
    """
    Base API exception.
    """
    status_code = 500


class RequestException(APIException):
    """
    Raised if request is invalid.
    """
    status_code = 400


class InvalidDatasetException(APIException):
    """
    Raised if the dataset specified in the request is invalid.
    """
    status_code = 404


class PredictionException(APIException):
    """
    Raised if the solver raises an exception.
    """
    status_code = 500


class InternalException(APIException):
    """
    Raised when an internal error occurs.
    """
    status_code = 500


class NotYetImplementedException(APIException):
    """
    Raised when the functionality has not yet been implemented.
    """
    status_code = 501


def rate_clip(rate, minimum_rate=0.2):
    """
    Lower-bound clipping for ascent and descent rates
    """

    if rate < minimum_rate:
        return minimum_rate
    else:
        return rate




# Request #####################################################################
@newrelic.agent.function_trace()
def parse_request(data):
    """
    Parse the request.
    """
    req = {"version": API_VERSION}

    # Generic fields
    req['launch_latitude'] = \
        _extract_parameter(data, "launch_latitude", float,
                           validator=lambda x: -90 <= x <= 90)
    req['launch_longitude'] = \
        _extract_parameter(data, "launch_longitude", float,
                           validator=lambda x: 0 <= x < 360)
    req['launch_datetime'] = \
        _extract_parameter(data, "launch_datetime", _rfc3339_to_timestamp)
    req['launch_altitude'] = \
        _extract_parameter(data, "launch_altitude", float, ignore=True)

    req['format'] = \
        _extract_parameter(data, "format", str, STANDARD_FORMAT)

    # If no launch altitude provided, use Ruaumoko to look it up
    if req['launch_altitude'] is None:
        try:
            req['launch_altitude'] = ruaumoko_ds().get(req['launch_latitude'],
                                                       req['launch_longitude'])
        except Exception:
            # Cannot query Ruaumoko - just set launch altitude to 0.
            req['launch_altitude'] = 0.0
            # raise InternalException("Internal exception experienced whilst " +
            #                         "looking up 'launch_altitude'.")

    # Prediction profile
    req['profile'] = _extract_parameter(data, "profile", str,
                                        PROFILE_STANDARD)

    launch_alt = req["launch_altitude"]

    if req['profile'] == PROFILE_STANDARD:
        req['ascent_rate'] = _extract_parameter(data, "ascent_rate", float,
                                                validator=lambda x: x > 0)
        req['burst_altitude'] = \
            _extract_parameter(data, "burst_altitude", float,
                               validator=lambda x: x > launch_alt)
        req['descent_rate'] = _extract_parameter(data, "descent_rate", float,
                                                 validator=lambda x: x > 0)
    elif req['profile'] == PROFILE_FLOAT:
        req['ascent_rate'] = _extract_parameter(data, "ascent_rate", float,
                                                validator=lambda x: x > 0)
        req['float_altitude'] = \
            _extract_parameter(data, "float_altitude", float,
                               validator=lambda x: x > launch_alt)
        req['stop_datetime'] = \
            _extract_parameter(data, "stop_datetime", _rfc3339_to_timestamp,
                               validator=lambda x: x > req['launch_datetime'])
    elif req['profile'] == PROFILE_REVERSE:
        req['ascent_rate'] = _extract_parameter(data, "ascent_rate", float,
                                                validator=lambda x: x > 0)
    else:
        raise RequestException("Unknown profile '%s'." % req['profile'])

    # Dataset
    req['dataset'] = _extract_parameter(data, "dataset", _rfc3339_to_timestamp,
                                        LATEST_DATASET_KEYWORD)


    return req

@newrelic.agent.function_trace()
def parse_request_ruaumoko(data):
    """
    Parse the request.
    """
    req = {"version": API_VERSION}

    # Generic fields
    req['latitude'] = \
        _extract_parameter(data, "latitude", float,
                           validator=lambda x: -90 <= x <= 90)
    req['longitude'] = \
        _extract_parameter(data, "longitude", float,
                           validator=lambda x: 0 <= x < 360)

    # Response dict
    resp = {
        "request": req,
    }

    warningcounts = WarningCounts()

    try:
        resp['altitude'] = ruaumoko_ds().get(req['latitude'],req['longitude'])
    except Exception:
        raise InternalException("Internal exception experienced whilst " +
                                "querying ruaumoko.")
    
    resp["warnings"] = warningcounts.to_dict()

    return resp

def parse_request_datasetcheck(data):
    """
    Dataset Check Request - try and find a dataset, any dataset, and return its info is there is one.
    """
    req = {"version": API_VERSION}

    # Response dict
    resp = {
        "request": req,
    }

    warningcounts = WarningCounts()

    # Find wind data location
    ds_dir = app.config.get('WIND_DATASET_DIR', WindDataset.DEFAULT_DIRECTORY)

    # Dataset
    try:
        tawhiri_ds = WindDataset.open_latest(persistent=True, directory=ds_dir)
        # Note that hours and minutes are set to 00 as Tawhiri uses hourly datasets
        resp['request']['dataset'] = \
            tawhiri_ds.ds_time.strftime("%Y-%m-%dT%H:00:00Z")
    except IOError:
        raise InvalidDatasetException("No matching dataset found.")
    except ValueError as e:
        raise InvalidDatasetException("Could not find any dataset.")
    except Exception as e:
        raise InvalidDatasetException("Could not find any dataset.")
    
    resp["warnings"] = warningcounts.to_dict()

    return resp
@newrelic.agent.function_trace()
def _extract_parameter(data, parameter, cast, default=None, ignore=False,
                       validator=None):
    """
    Extract a parameter from the POST request and raise an exception if any
    parameter is missing or invalid.
    """
    if parameter not in data:
        if default is None and not ignore:
            raise RequestException("Parameter '%s' not provided in request." %
                                   parameter)
        return default

    try:
        result = cast(data[parameter])
    except Exception:
        raise RequestException("Unable to parse parameter '%s': %s." %
                               (parameter, data[parameter]))

    if validator is not None and not validator(result):
        raise RequestException("Invalid value for parameter '%s': %s." %
                               (parameter, data[parameter]))

    return result


# Response ####################################################################
@newrelic.agent.function_trace()
def run_prediction(req):
    """
    Run the prediction.
    """
    # Response dict
    resp = {
        "request": req,
        "prediction": [],
    }

    warningcounts = WarningCounts()

    # Find wind data location
    ds_dir = app.config.get('WIND_DATASET_DIR', WindDataset.DEFAULT_DIRECTORY)

    # Dataset
    try:
        if req['dataset'] == LATEST_DATASET_KEYWORD:
            tawhiri_ds = WindDataset.open_latest(persistent=True, directory=ds_dir)
        else:
            tawhiri_ds = WindDataset(datetime.fromtimestamp(req['dataset']), directory=ds_dir)
    except IOError:
        raise InvalidDatasetException("No matching dataset found.")
    except ValueError as e:
        raise InvalidDatasetException(*e.args)

    # Note that hours and minutes are set to 00 as Tawhiri uses hourly datasets
    resp['request']['dataset'] = \
            tawhiri_ds.ds_time.strftime("%Y-%m-%dT%H:00:00Z")

    # Stages
    if req['profile'] == PROFILE_STANDARD:
        stages = models.standard_profile(req['ascent_rate'],
                                         req['burst_altitude'],
                                         req['descent_rate'],
                                         tawhiri_ds,
                                         ruaumoko_ds(),
                                         warningcounts)
    elif req['profile'] == PROFILE_FLOAT:
        stages = models.float_profile(req['ascent_rate'],
                                      req['float_altitude'],
                                      req['stop_datetime'],
                                      tawhiri_ds,
                                      warningcounts)
    elif req['profile'] == PROFILE_REVERSE:
        stages = models.reverse_profile(req['ascent_rate'],
                                      tawhiri_ds,
                                      ruaumoko_ds(),
                                      warningcounts)
    else:
        raise InternalException("No implementation for known profile.")

    # Run solver
    try:
        profile_solve = newrelic.agent.ProfileTraceWrapper(solver.solve)
        if req['profile'] == PROFILE_REVERSE:
            # For the reverse prediction we simply set the time-step to be negative!
            result = profile_solve(req['launch_datetime'], req['launch_latitude'],
                                req['launch_longitude'], req['launch_altitude'],
                                stages)
        else:
            result = profile_solve(req['launch_datetime'], req['launch_latitude'],
                                req['launch_longitude'], req['launch_altitude'],
                                stages)

    except Exception as e:
        raise PredictionException("Prediction did not complete: '%s'." %
                                  str(e))

    # Format trajectory
    if req['profile'] == PROFILE_STANDARD:
        resp['prediction'] = _parse_stages(["ascent", "descent"], result)
    elif req['profile'] == PROFILE_FLOAT:
        resp['prediction'] = _parse_stages(["ascent", "float"], result)
    elif req['profile'] == PROFILE_REVERSE:
        resp['prediction'] = _parse_stages(["ascent", "descent"], result)
        # Extract the last entry as our launch site estimate.
        _launch_site = resp['prediction'][-1]['trajectory'][-1]
        resp['launch_estimate'] = {
            'latitude': _launch_site['latitude'], 
            'longitude': _launch_site['longitude'],
            'altitude': _launch_site['altitude'],
            'datetime': _timestamp_to_rfc3339(req['launch_datetime'])
        }

    else:
        raise InternalException("No implementation for known profile.")

    # Convert request UNIX timestamps to RFC3339 timestamps
    for key in resp['request']:
        if "datetime" in key:
            resp['request'][key] = _timestamp_to_rfc3339(resp['request'][key])

    resp["warnings"] = warningcounts.to_dict()

    return resp

@newrelic.agent.function_trace()
def _parse_stages(labels, data):
    """
    Parse the predictor output for a set of stages.
    """
    assert len(labels) == len(data)

    prediction = []
    for index, leg in enumerate(data):
        stage = {}
        stage['stage'] = labels[index]
        stage['trajectory'] = [{
            'latitude': lat,
            'longitude': lon,
            'altitude': alt,
            'datetime': _timestamp_to_rfc3339(dt),
            } for dt, lat, lon, alt in leg]
        prediction.append(stage)
    return prediction


# Flask App ###################################################################
@app.route('/api/v{0}/'.format(API_VERSION), methods=['GET'])
def main():
    """
    Single API endpoint which accepts GET requests.
    """
    newrelic.agent.capture_request_params()
    g.request_start_time = time.time()
    response = run_prediction(parse_request(request.args))
    g.request_complete_time = time.time()
    response['metadata'] = _format_request_metadata()

    # Format the result data as per the users request
    if response["request"]["format"] == "csv":
        _formatted = format_csv(fix_data_longitudes(response))
        return send_file(
            BytesIO(_formatted['data'].encode()),
            mimetype="text/csv",
            as_attachment=True,
            attachment_filename=_formatted['filename']
        )

    elif response["request"]["format"] == "kml":
        _formatted = format_kml(fix_data_longitudes(response))
        return send_file(
            BytesIO(_formatted['data'].encode()),
            as_attachment=True,
            attachment_filename=_formatted['filename']
        )

    elif response["request"]["format"] == "json":
        return jsonify(response)
    else:
        raise InternalException("Format not supported: " + response["request"]["format"])



@app.route('/api/ruaumoko/', methods=['GET'])
def main_ruaumoko():
    """
    Ruaumoko endpoint
    """
    g.request_start_time = time.time()
    response = parse_request_ruaumoko(request.args)
    g.request_complete_time = time.time()
    response['metadata'] = _format_request_metadata()
    return jsonify(response)

@app.route('/api/datasetcheck', methods=['GET'])
def main_datasetcheck():
    """
    Dataset Check Endpoint
    """
    g.request_start_time = time.time()
    response = parse_request_datasetcheck(request.args)
    g.request_complete_time = time.time()
    response['metadata'] = _format_request_metadata()
    return jsonify(response)


@app.errorhandler(APIException)
def handle_exception(error):
    """
    Return correct error message and HTTP status code for API exceptions.
    """
    response = {}
    response['error'] = {
        "type": type(error).__name__,
        "description": str(error)
    }
    g.request_complete_time = time.time()
    response['metadata'] = _format_request_metadata()
    return jsonify(response), error.status_code


# Uncomment for local testing
# @app.after_request # blueprint can also be app~~
# def after_request(response):
#     header = response.headers
#     header['Access-Control-Allow-Origin'] = '*'
#     return response

@newrelic.agent.function_trace()
def _format_request_metadata():
    """
    Format the request metadata for inclusion in the response.
    """
    return {
        "start_datetime": _timestamp_to_rfc3339(g.request_start_time),
        "complete_datetime": _timestamp_to_rfc3339(g.request_complete_time),
    }
