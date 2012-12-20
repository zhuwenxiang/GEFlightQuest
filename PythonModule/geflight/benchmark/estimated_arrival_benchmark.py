import csv
import os
import pandas as pd

from datetime import datetime
from dateutil.tz import tzutc
from dateutil.parser import parse

from geflight.transform import flighthistory, flighthistoryevents
from geflight.transform import utilities as tu
from geflight.benchmark import utilities as bu

import numpy as np

def get_test_flight_ids(test_day_path):
    reader = csv.reader(open(os.path.join(test_day_path, "test_flights.csv")))
    # ignore header
    reader.next()
    return [int(row[0]) for row in reader]

def get_test_days(test_days_path):
    return os.walk(test_day_path).next()[1]

def get_df_test_days(test_days_path):
    return pd.read_csv(os.path.join(test_days_path, "days.csv"),
        converters={"selected_cutoff_time": parse})

def get_other_arrival_type(arrival_type):
    if arrival_type == "runway":
        return "gate"
    return "runway"

def get_scheduled_arrival(row, arrival_type, cutoff_time):
    if row["scheduled_%s_arrival" % arrival_type] != "MISSING":
        return row["scheduled_%s_arrival" % arrival_type]
    if row["scheduled_%s_arrival" % get_other_arrival_type(arrival_type)] != "MISSING":
        return row["scheduled_%s_arrival" % get_other_arrival_type(arrival_type)]
    if row["published_arrival"] != "MISSING":
        return row["published_arrival"]
    return cutoff_time 

def get_estimated_arrival_time(row, arrival_type, cutoff_time):
    if row["estimated_%s_arrival" % arrival_type] != "MISSING":
        return row["estimated_%s_arrival" % arrival_type]
    if row["estimated_%s_arrival" % get_other_arrival_type(arrival_type)] != "MISSING":
        return row["estimated_%s_arrival" % get_other_arrival_type(arrival_type)]
    return get_scheduled_arrival(row, arrival_type, cutoff_time)

def process_day(test_day_path, cutoff_time):
    """
    For each day we 
    """
    midnight_time = datetime(cutoff_time.year, cutoff_time.month, cutoff_time.day, tzinfo=tzutc())

    test_flights_list = get_test_flight_ids(test_day_path)
    test_flights_set = set(test_flights_list)

    df_flight_history = flighthistory.get_df_flight_history_from_train_format(
        os.path.join(test_day_path, "FlightHistory", "flighthistory.csv"))
    df_flight_history.index = df_flight_history["flight_history_id"]
    test_flights_index = pd.Index(data = test_flights_list, name="flight_history_id")
    df_test_flights = pd.DataFrame(None, index=test_flights_index)
    df_test_flights = df_test_flights.join(df_flight_history)
    df_test_flights = df_test_flights.join(pd.Series(
        data=["MISSING" for i in range(len(df_test_flights))],
        index=df_test_flights.index, name="estimated_runway_arrival"))
    df_test_flights = df_test_flights.join(pd.Series(
        data=["MISSING" for i in range(len(df_test_flights))],
        index=df_test_flights.index, name="estimated_gate_arrival"))

    df_fhe = pd.read_csv(os.path.join(test_day_path, "FlightHistory", 
        "flighthistoryevents.csv"))

    for i, row in df_fhe.iterrows():
        f_id = row["flight_history_id"]
        if f_id not in df_test_flights.index:
            continue
        if type(row["data_updated"]) != str:
            continue
        offset = df_test_flights["arrival_airport_timezone_offset"][f_id]
        if offset>0:
            offset_str = "+" + str(offset)
        else:
            offset_str = str(offset)
        gate_str = flighthistoryevents.get_estimated_gate_arrival_string(row["data_updated"])
        if gate_str:
            df_test_flights["estimated_gate_arrival"][f_id] = parse(gate_str+offset_str)
        runway_str = flighthistoryevents.get_estimated_runway_arrival_string(row["data_updated"])
        if runway_str:
            df_test_flights["estimated_runway_arrival"][f_id] = parse(runway_str+offset_str)

    print("Gate Not Missing: %d" % sum(df_test_flights["estimated_gate_arrival"] != "MISSING"))
    print("Runway Not Missing: %d" % sum(df_test_flights["estimated_runway_arrival"] != "MISSING"))

    for i, row in df_test_flights.iterrows():
        df_test_flights["actual_runway_arrival"][i] = get_estimated_arrival_time(row, "runway", cutoff_time)
        df_test_flights["actual_gate_arrival"][i] = get_estimated_arrival_time(row, "gate", cutoff_time)

    df_day_prediction = df_test_flights[["flight_history_id"
                    , "actual_runway_arrival"
                    , "actual_gate_arrival"]]

    for i in df_day_prediction.index:
        df_day_prediction["actual_runway_arrival"][i] = tu.minutes_difference(df_day_prediction["actual_runway_arrival"][i], midnight_time)
        df_day_prediction["actual_gate_arrival"][i] = tu.minutes_difference(df_day_prediction["actual_gate_arrival"][i], midnight_time)

    return df_day_prediction

def run_benchmark():
    test_data_path = os.path.join(os.environ["DataPath"],
        "GEFlight", "Release 2", "PublicLeaderboardSet")
    df_test_days = get_df_test_days(test_data_path)

    df_predictions = []

    for i, row in df_test_days.iterrows():
        print(row["folder_name"])
        df_predictions.append(process_day(
            os.path.join(test_data_path, row["folder_name"]),
            row["selected_cutoff_time"]))

    df_out = df_predictions[0]
    for df in df_predictions[1:]:
        df_out = df_out.append(df, ignore_index=True)
    df_out = df_out.sort("flight_history_id")
    df_out.to_csv(os.path.join(os.environ["DataPath"], "GEFlight", "estimated_arrival_benchmark.csv"), index=False)

if __name__=="__main__":
    run_benchmark()