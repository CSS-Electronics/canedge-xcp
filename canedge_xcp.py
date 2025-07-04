import argparse
from utils import CANedgeXCP
from pathlib import Path
import math
import os, json

# Parse command-line arguments
def parse_args():
    parser = argparse.ArgumentParser(description="XCP script for generating CANedge transmit list and DBC for dynamic DAQ lists.")

    # Required positional arguments
    parser.add_argument("output_dbc", type=Path, help="Path for outputting DBC file. Example: path/to/mydbc.dbc")
    parser.add_argument("output_transmit", type=Path, help="Path for outputting transmit list JSON file. Example: path/to/transmit_list.json")
    parser.add_argument("signal_file", type=Path, help="Path to the CSV-style signal file to use for filtering signals. Example: path/to/signal_file.csv")
    parser.add_argument("--a2l", type=Path, nargs="+", required=True, help="One or more A2L files. Example: --a2l abc.a2l xyz.a2l.")
    parser.add_argument("--default_params", type=Path, default=Path("a2l_params_default.json"), help="Path to default a2l parameters JSON file used when A2L file lacks XCP_ON_CAN section. Default: a2l_params_default.json")

    return parser.parse_args()

# Main execution
if __name__ == "__main__":
    args = parse_args()

    # Ensure paths are absolute
    output_dbc = args.output_dbc.resolve()
    output_transmit = args.output_transmit.resolve()
    signal_file = args.signal_file.resolve()
    a2l_files = [path.resolve() for path in args.a2l]
    default_params_file = args.default_params.resolve()

    # Print parsed arguments for debugging
    print("\nParsed arguments:")
    print(f"Output DBC: {output_dbc}")
    print(f"Output transmit list: {output_transmit}")
    print(f"Signal file: {signal_file}")
    print(f"A2L file(s): {a2l_files}")
    print(f"Default params file: {default_params_file}\n")

    # Ensure signal file exists
    if not signal_file.exists():
        raise FileNotFoundError(f"Signal file not found: {signal_file}")

    # Settings for script
    settings = {
        "start_delay": 1000,     # ms before the first CTO
        "frame_spacing": 10,     # ms between each CTO
        "max_frames": 224,       # limit based on CANedge FW 01.09.01+
        "max_data_bytes": 4096,  # limit based on CANedge FW 01.09.01+
        "shorten_signals": True  # shorten DBC signal names to 32 chars
    }
    
    # Initialize CANedgeXCP Class
    cxcp = CANedgeXCP(a2l_files, signal_file, default_params_file)

    # Load A2L files into dictionary, load general XCP parameters/signals/computation methods, then filter signals based on signal filter list
    a2l_dict = cxcp.load_a2l_files()
    a2l_params = cxcp.load_a2l_params(a2l_dict)
    a2l_compu_methods = cxcp.load_a2l_compu_methods(a2l_dict)
    a2l_signals_all = cxcp.load_a2l_signals(a2l_dict, a2l_compu_methods)
    user_signals = cxcp.load_signal_file()
    signals = cxcp.filter_a2l_signals(a2l_signals_all, user_signals, a2l_params)

    # Optionally hardcode MAX_CTO and MAX_DTO
    # a2l_params["MAX_CTO"] = "0x40"
    # a2l_params["MAX_DTO"] = "0x0040"
    
    print(f"\nRequested signals: {len(user_signals)} | Available signals: {len(a2l_signals_all)} | Matched signals: {len(signals)} ({math.floor((len(signals)/len(user_signals))*100)}%)")
    print(f"A2L settings: MAX_CTO: {int(a2l_params['MAX_CTO'],16)} | MAX_DTO: {int(a2l_params['MAX_DTO'],16)} | BYTE_ORDER: {a2l_params['BYTE_ORDER']} | CAN_FD: {a2l_params['CAN_FD']}\n")

    # Generate status CSV showing which signals were matched/not matched
    status_csv_path = cxcp.create_status_csv(user_signals)
    
    # Group the signals by assigning them to DAQ and ODT lists
    signals_grouped = cxcp.group_signals(signals, a2l_params)

    # Construct dynamic DAQ initialization CAN frames
    daq_frames = cxcp.create_daq_frames(signals_grouped, a2l_params)

    # Create and save outputs
    cxcp.create_transmit_list(daq_frames, a2l_params, settings, output_transmit)
    cxcp.create_dbc(signals_grouped, a2l_params, output_dbc, settings)
