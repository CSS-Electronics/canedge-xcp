class CANedgeXCP:
    # Initialize class
    def __init__(self, a2l_files, signal_file, default_params_file=None):
        self.a2l_files = a2l_files 
        self.signal_file = signal_file
        self.default_params_file = default_params_file
        self.matched_signals = set()  # Store matched signal names
        self.data_type_map = {
            "uchar": ("unsigned", 1),
            "schar": ("signed", 1),
            "ubyte": ("unsigned", 1),
            "sbyte": ("signed", 1),
            "uword": ("unsigned", 2),
            "sword": ("signed", 2),
            "slong": ("signed", 4),
            "a_uint64": ("unsigned", 8),
            "a_int64": ("signed", 8),
            "char": ("signed", 1),
            "uint": ("unsigned", 2),
            "int": ("signed", 2),
            "ulong": ("unsigned", 4),
            "long": ("signed", 4),
            "float": ("float", 4),
            "float32_ieee": ("float", 4),
            "float64_ieee": ("double", 8)
        }
        
    # ----------------------------------
    # helper function to clean output directory
    def clean_output_directory(self, output_dir):
        import shutil
        if output_dir.exists() and output_dir.is_dir():
            for file in output_dir.iterdir():
                if file.is_file():
                    file.unlink() 
                elif file.is_dir():
                    shutil.rmtree(file) 

            
    # ----------------------------------
    # helper function for loading elements from A2L
    def get_next_value(self,data_list, key):
        try:
            index = data_list.index(key)
            return data_list[index + 1]
        except (ValueError, IndexError):
            return None  # Return None if key is not found or no next value exists
        
    # ----------------------------------
    # helper function for forcing integer value from A2L   
    def force_int(self, element):
        return int(element, 16) if isinstance(element, str) and element.startswith("0x") else int(element)
    
    # ----------------------------------
    # helper function for formatting numbers      
    def format_number(self,value):
        value = round(value, 10)  # Ensure full decimal precision
        return "{:.10f}".format(value).rstrip('0').rstrip('.')  # Remove trailing zeros
                
    # ----------------------------------
    # helper function for parsing A2L CAN IDs       
    def extract_can_id(self,can_id_str):
        can_id = int(can_id_str, 16)  # Convert string hex to integer
        
        if can_id & 0x80000000:  # Check if it's an extended ID (MSB set)
            return hex(can_id & 0x1FFFFFFF), True  # Extract 29-bit ID
        else:
            return hex(can_id & 0x7FF), False  # Extract 11-bit ID
    
    # ----------------------------------
    # function for loading A2L files into dictionary
    def load_a2l_files(self):
        from a2lparser.a2lparser import A2LParser
        from a2lparser.a2lparser_exception import A2LParserException
        import sys

        sys.stdout.reconfigure(encoding="utf-8")

        a2l_dict = {}

        try:
            parser = A2LParser(log_level="INFO")
            for a2l_file in self.a2l_files:
                a2l_file = str(a2l_file)  # Ensure it's a string path
                parsed_data = parser.parse_file(a2l_file)

                # Merge parsed_data into a2l_dict
                a2l_dict.update(parsed_data)  # parsed_data is already a dictionary

            return a2l_dict

        except A2LParserException as ex:
            print(f"Error parsing A2L file: {ex}")
            return {}
 
    # ----------------------------------
    # function for loading general XCP parameters from A2L files
    def load_a2l_params(self, a2l_dict):     
        import json, sys, os
        
        a2l_params = {} 
        
        try:
            # Attempt to extract parameters from A2L file
            for a2l_file_name, ast in a2l_dict.items():
                
                if_data = ast["PROJECT"]["MODULE"]["IF_DATA"]
                
                # Ensure IF_DATA is a list or dictionary and standardize to a list for easier handling
                if isinstance(if_data, dict):
                    if_data = [if_data]
                
                # Get XCP_ON_CAN section and extract relevant information
                xcp = next((entry for entry in if_data if "XCP_ON_CAN" in entry), None)
                if xcp is None:
                    raise Exception("XCP_ON_CAN section not found in A2L file")
                    
                xcp_on_can = xcp["XCP_ON_CAN"]
                a2l_params["CAN_ID_MASTER"], a2l_params["CAN_ID_MASTER_EXTENDED"] = self.extract_can_id(self.get_next_value(xcp_on_can["DataParams"], "CAN_ID_MASTER"))
                a2l_params["CAN_ID_SLAVE"], a2l_params["CAN_ID_SLAVE_EXTENDED"] = self.extract_can_id(self.get_next_value(xcp_on_can["DataParams"], "CAN_ID_SLAVE"))
                a2l_params["XCP_VERSION"] = xcp_on_can["DataParams"][0]
                a2l_params["BAUDRATE"] = self.force_int(self.get_next_value(xcp_on_can["DataParams"], "BAUDRATE")) 
                
                # Attempt to extract PROTOCOL_LAYER and EVENT sections from XCP_ON_CAN sub section - otherwise default to general XCP section
                try: 
                    protocol_layer = xcp_on_can["PROTOCOL_LAYER"]["DataParams"]
                    events = xcp_on_can["DAQ"]["EVENT"] 
                except:
                    protocol_layer = xcp["PROTOCOL_LAYER"]["DataParams"]
                    events = xcp["DAQ"]["EVENT"] 
                    print("WARNING: Unable to extract PROTOCOL_LAYER and DAQ from XCP_ON_CAN - extracting instead from general XCP settings")
                    
                # Add event data to list
                event_data = []
                for event in events:
                    event_data.append({"EventName": event["DataParams"][0].strip('"'), "EventChannelNumber": self.force_int(event["DataParams"][2]), "EventPriority": f"0x{self.force_int(event['DataParams'][7]):02X}"})
                
                if "WRITE_DAQ_MULTIPLE" in protocol_layer:
                    a2l_params["WRITE_DAQ_MULTIPLE"] = True 
                else:  
                    a2l_params["WRITE_DAQ_MULTIPLE"] = False
                      
                a2l_params["BYTE_ORDER"] = 'big' if protocol_layer[10] == 'BYTE_ORDER_MSB_FIRST' else 'little'
                a2l_params["EVENTS"] = event_data                
                
                # Assign CAN FD related information (if available)
                try: 
                    can_fd_entry = xcp_on_can["CAN_FD"]["DataParams"]
                    a2l_params["CAN_FD"] = True 
                    a2l_params["CAN_FD_DATA_TRANSFER_BAUDRATE"] = self.force_int(self.get_next_value(can_fd_entry,"CAN_FD_DATA_TRANSFER_BAUDRATE"))
                except:
                    a2l_params["CAN_FD"] = False 
                    a2l_params["CAN_FD_DATA_TRANSFER_BAUDRATE"] = None
                
                # Assign MAX_CTO
                if a2l_params["CAN_FD"] == False or a2l_params["WRITE_DAQ_MULTIPLE"] == False:
                    a2l_params["MAX_CTO"] = "0x08"
                else:
                    a2l_params["MAX_CTO"] = "0x0040" 
        
                # Assign MAX_DTO
                if a2l_params["CAN_FD"] == False:
                    a2l_params["MAX_DTO"] = "0x0008"
                else:
                    a2l_params["MAX_DTO"] = "0x0040" 
                                    
            return a2l_params
            
        except Exception as e:
            # If there's an error extracting from A2L, load from default JSON file
            if self.default_params_file is None or not os.path.exists(self.default_params_file):
                print(f"\nERROR: Failed to extract a2l_params from A2L: {str(e)}")
                print("ERROR: No default params file provided or file does not exist.")
                sys.exit(1)
                
            try:
                print(f"\nWARNING: Failed to extract a2l_params from A2L: {str(e)}")
                print(f"WARNING: Loading default parameters from {self.default_params_file}")
                print("WARNING: Please review the default parameters to ensure they are valid for your ECU!")
                
                with open(self.default_params_file, 'r') as f:
                    a2l_params = json.load(f)
                return a2l_params
                
            except Exception as json_e:
                print(f"ERROR: Failed to load default parameters: {str(json_e)}")
                sys.exit(1)
    
    # ----------------------------------
    # function for loading all computation methods from A2L files
    def load_a2l_compu_methods(self, a2l_dict):
        import json, sys 
        signal_scaling = []
        
        for a2l_file_name, ast in a2l_dict.items():
            compu_methods = ast.find_sections("COMPU_METHOD")["COMPU_METHOD"]
            # print(json.dumps(compu_methods,indent=4))
            
            for method in compu_methods:
                conversion_type = method.get("ConversionType", "")
                unit = method.get("UNIT", "").strip('"')  # Remove surrounding quotes from UNIT
            
                
                if conversion_type == "LINEAR":
                    coeffs = method.get("COEFFS_LINEAR", {})
                    scale = float(coeffs.get("a", 0))
                    offset = float(coeffs.get("b", 0))
                    
                    # Ensure offset is 0 instead of -0.0
                    offset = 0 if offset == -0.0 or offset == 0.0 else offset
                    
                    signal_scaling.append({
                        "Name": method["Name"],
                        "Unit": unit,
                        "Scale": self.format_number(scale),
                        "Offset": self.format_number(offset)
                    })
                
                elif conversion_type == "RAT_FUNC":
                    coeffs = method.get("COEFFS", {})

                    if all(float(coeffs.get(k, 0)) == 0 for k in ["a", "d", "e"]):
                        b = float(coeffs.get("b", 1))
                        f = float(coeffs.get("f", 1))
                        c = float(coeffs.get("c", 0))
                        scale = f / b if b != 0 else 0
                        offset = -c / b if b != 0 else 0
                        
                        # Ensure offset is 0 instead of -0.0
                        offset = 0 if offset == -0.0 or offset == 0.0 else offset
                        
                        signal_scaling.append({
                            "Name": method["Name"],
                            "Unit": unit,
                            "Scale": self.format_number(scale),
                            "Offset": self.format_number(offset)
                        })
        
        return signal_scaling
            
    # ----------------------------------
    # function for loading all signals from multiple A2L files
    def load_a2l_signals(self, a2l_dict, a2l_compu_methods):        
        signals = {}
        
        # Create a lookup dictionary for computation methods
        compu_methods_lookup = {method["Name"]: method for method in a2l_compu_methods}
        
        for a2l_file_name, ast in a2l_dict.items():
            print(f"A2L file: {a2l_file_name} | Project: {ast['PROJECT']['Name']} | Module: {ast['PROJECT']['MODULE']['Name']}")
            
            signals_partial = ast.find_sections("MEASUREMENT")["MEASUREMENT"]
            
            # Keep only unique Name entries, overwriting duplicates
            for signal in signals_partial:
                signals[signal["Name"]] = signal
            
        new_signals = []
        for signal in signals.values():
            dt = signal.get("Datatype", "").strip().lower()
            signage, length = self.data_type_map.get(dt, ("unknown", 0))

            new_signal = {}
            for key, value in signal.items():
                new_signal[key] = value
                if key == "Name":
                    new_signal["Signage"] = signage
                    new_signal["Length"] = length
                    
                    # Lookup computation method using CONVERSION value
                    compu_method = compu_methods_lookup.get(signal.get("CONVERSION", ""))
                    if compu_method:
                        new_signal["Scale"] = compu_method["Scale"]
                        new_signal["Offset"] = compu_method["Offset"]
                        new_signal["Unit"] = compu_method["Unit"]
                    else:
                        new_signal["Scale"] = 1  # Default scale if no match found
                        new_signal["Offset"] = 0  # Default offset if no match found
                        new_signal["Unit"] = ""  # Default unit if no match found
            
            new_signals.append(new_signal)
        
        return new_signals
                
    # ----------------------------------
    # function for loading file with filtered signals provided by user
    def load_signal_file(self):
        import csv
        import sys

        # Ensure the file exists
        if not self.signal_file.exists():
            print(f"Error: Signal file {self.signal_file} not found.")
            sys.exit()

        csv_mapping = {}
        
        # Read CSV file
        with self.signal_file.open(newline='', encoding='utf-8') as csvfile:
            reader = csv.reader(csvfile, delimiter=";")
            for row in reader:
                if len(row) < 2 or not row[0].strip() or "[" in row[0]:  # Skip headers and empty rows
                    continue
                name, event = row[0].strip(), row[1].strip()
                csv_mapping[name] = event  # Store event as a string

        return csv_mapping


    
    # ----------------------------------
    # function for filtering A2L signals based on filter list (and adding event ID as EventConfigured)
    def filter_a2l_signals(self,a2l_signals_all, user_signals, a2l_params):  
        import json   
        
        # Clear previously matched signals
        self.matched_signals = set()
        
        max_dto = min(int(a2l_params["MAX_DTO"], 16),64)
        signals_filtered_dict = {}
        for signal in a2l_signals_all:
            signal_name = signal.get("Name", "").strip()
            if signal_name in user_signals:
                if signal_name not in signals_filtered_dict:
                    # Create a new dictionary with "Name" and "EventConfigured" first.
                    new_signal = {}
                    new_signal["Name"] = signal_name
                    new_signal["EventConfigured"] = user_signals[signal_name]
                    # Add all other key/value pairs from the original signal.
                    for key, value in signal.items():
                        if key != "Name":
                            new_signal[key] = value
                    
                    if new_signal.get("Length", 0) == 0:
                        print(f"Warning: Removed {signal_name} (length of 0)")
                        continue
                    if new_signal.get("Length", 0) == 8 and max_dto == 8:
                        print(f"Warning: Removed {signal_name} (length of 8) as MAX_DTO is 8 i.e. MAX_ODT_ENTRY_SIZE_DAQ = 7")
                        continue
                    
                    signals_filtered_dict[signal_name] = new_signal
                    # Add to matched signals set
                    self.matched_signals.add(signal_name)

        signals_filtered = list(signals_filtered_dict.values())       
            
        return signals_filtered
    
    # ----------------------------------
    # function for grouping filtered signals into DAQ and ODT lists
    def group_signals(self, signals, a2l_params):
        from collections import defaultdict
        import sys
        
        if len(signals) == 0:
            print("No matched signals - exiting script!")
            sys.exit()

        max_dto = min(int(a2l_params["MAX_DTO"], 16),64) # cannot be more than 64 bytes for CAN FD
        max_payload = max_dto - 1  # Account for the 1-byte PID
        
        # Group signals by EVENT_CHANNEL_NUMBER (using EventConfigured value)
        daq_lists = defaultdict(list)
        for signal in signals:
            event_channel = signal['EventConfigured'] 
            daq_lists[event_channel].append(signal)
        
        signals_grouped = []
        daq_counter = 0
        
        # Assign DAQ lists and ODTs
        for event_channel, event_signals in daq_lists.items():
            odt_counter = 0
            current_odt_size = 0
            odt_entries = []
            
            for signal in event_signals:
                signal_length = signal['Length']
                
                # If adding this signal exceeds the max payload, start a new ODT
                if current_odt_size + signal_length > max_payload:
                    odt_counter += 1
                    current_odt_size = 0
                    odt_entries = []
                    
                # Assign DAQ, ODT, and ODT_ENTRY_NUMBER
                odt_entry_number = len(odt_entries)
                
                signal['DAQ_LIST_NUMBER'] = f"0x{daq_counter:04X}"
                signal['ODT_NUMBER'] = f"0x{odt_counter:02X}"
                signal['ODT_ENTRY_NUMBER'] = f"0x{odt_entry_number:02X}"
                
                odt_entries.append(signal)
                current_odt_size += signal_length
                signals_grouped.append(signal)
            
            daq_counter += 1
        
        return signals_grouped


    # ----------------------------------
    # function for creating the actual DAQ initialization CAN frames
    def create_daq_frames(self, signals_grouped, a2l_params):
        daq_frames = []
        byte_order = a2l_params['BYTE_ORDER'] 
        max_cto = min(int(a2l_params['MAX_CTO'], 16),64)
        max_payload_size = 64 - 1  # Max CAN FD frame size minus 1 byte for command ID
        
        # Hardcoded values
        address_extension = "00"
        prescaler = "01"
        start_stop_mode = "02"
        bit_offset = "FF"
        dummy_byte = "00"
        
        # Generic initialization commands
        daq_frames.append({"Name": "CONNECT", "DATA": "FF00"})
        daq_frames.append({"Name": "GET_STATUS", "DATA": "FD"})
        daq_frames.append({"Name": "FREE_DAQ", "DATA": "D6"})
        
        # AL_DAQ (0xD5 commands)
        daq_lists = sorted(set(signal['DAQ_LIST_NUMBER'] for signal in signals_grouped))
        daq_count = len(daq_lists).to_bytes(2, byte_order).hex().upper()
        daq_frames.append({"Name": "AL_DAQ", "DATA": f"D500{daq_count}"})
        
        # AL_ODT and AL_ODT_ENTRY (0xD4 commands)
        for daq_list in daq_lists:
            odts = sorted(set(signal['ODT_NUMBER'] for signal in signals_grouped if signal['DAQ_LIST_NUMBER'] == daq_list))
            daq_number = int(daq_list, 16).to_bytes(2, byte_order).hex().upper()
            
            daq_frames.append({"Name": f"AL_ODT_{daq_list}", "DATA": f"D400{daq_number}{len(odts):02X}"})
        
        # AL_ODT_ENTRY (0xD3 commands)
        for daq_list in daq_lists:
            odts = sorted(set(signal['ODT_NUMBER'] for signal in signals_grouped if signal['DAQ_LIST_NUMBER'] == daq_list))
            daq_number = int(daq_list, 16).to_bytes(2, byte_order).hex().upper()
            for odt in odts:
                
                entries = [signal for signal in signals_grouped if signal['DAQ_LIST_NUMBER'] == daq_list and signal['ODT_NUMBER'] == odt]
                odt_number = int(odt, 16).to_bytes(1, 'big').hex().upper()
                
                daq_frames.append({"Name": f"AL_ODT_ENT_{odt}", "DATA": f"D300{daq_number}{odt_number}{len(entries):02X}"})
        
        # SET_DAQ_PTR once per ODT, followed by multiple WRITE_DAQ or WRITE_DAQ_MULTIPLE commands
        for daq_list in daq_lists:
            daq_signals = [s for s in signals_grouped if s['DAQ_LIST_NUMBER'] == daq_list]
            
            odts = sorted(set(s['ODT_NUMBER'] for s in daq_signals))
            for odt in odts:
                odt_signals = [s for s in daq_signals if s['ODT_NUMBER'] == odt]
                daq_number = int(daq_list, 16).to_bytes(2, byte_order).hex().upper()
                odt_number = int(odt, 16).to_bytes(1, 'big').hex().upper()
                
                daq_frames.append({"Name": "SET_DAQ_PTR", "DATA": f"E200{daq_number}{odt_number}00"})
                
                if max_cto == 64:
                    frame_data = []
                    for signal in odt_signals:
                        length = int(signal['Length'])  # Ensure length is a valid integer, default to 1
                        ecu_address = int(signal['ECU_ADDRESS'], 16).to_bytes(4, byte_order).hex().upper()
                        signal_entry = f"{bit_offset}{length:02X}{ecu_address}{address_extension}{dummy_byte}"
                        
                        if len("".join(frame_data) + signal_entry) // 2 > max_payload_size:
                            daq_frames.append({"Name": "WRITE_DAQ_MULTI", "DATA": f"C7{len(frame_data):02X}{''.join(frame_data)}".ljust(128, '0')[:128]})
                            frame_data = []
                        
                        frame_data.append(signal_entry)
                    
                    if frame_data:
                        daq_frames.append({"Name": "WRITE_DAQ_MULTI", "DATA": f"C7{len(frame_data):02X}{''.join(frame_data)}".ljust(128, '0')[:128]})
                else:
                    for idx, signal in enumerate(odt_signals):
                        length = int(signal['Length']) 
                        ecu_address = int(signal['ECU_ADDRESS'], 16).to_bytes(4, byte_order).hex().upper()                        
                        daq_frames.append({"Name": f"WRITE_DAQ_0x{idx:02X}", "DATA": f"E1FF{length:02X}{address_extension}{ecu_address}"})

        # SET_DAQ_LIST_MODE (now with correct priority lookup)
        for daq_list in daq_lists:
            event_channel = int(next(s for s in signals_grouped if s['DAQ_LIST_NUMBER'] == daq_list)['EventConfigured'], 16)
            
            # Lookup priority in a2l_params["EVENTS"]
            event_priority = "00"  # Default
            for event in a2l_params["EVENTS"]:
                if int(event["EventChannelNumber"]) == event_channel:
                    event_priority = event["EventPriority"].upper().replace("0X", "")
                    break  # Stop searching once a match is found
            
            daq_number = int(daq_list, 16).to_bytes(2, byte_order).hex().upper()
            event_channel_hex = event_channel.to_bytes(2, byte_order).hex().upper()
            
            daq_frames.append({"Name": "SET_DAQ_LIST_MOD", "DATA": f"E000{daq_number}{event_channel_hex}{prescaler}{event_priority}"})

        # START_STOP_DAQ_LIST
        for daq_list in daq_lists:
            daq_number = int(daq_list, 16).to_bytes(2, byte_order).hex().upper()
            daq_frames.append({"Name": "START_STOP_DAQ", "DATA": f"DE{start_stop_mode}{daq_number}"})

        # START_STOP_SYNC
        daq_frames.append({"Name": "START_STOP_SYNCH", "DATA": "DD01"})
        
        return daq_frames




    # ----------------------------------
    # function for creating CANedge transmit list 
    def create_transmit_list(self, daq_frames, a2l_params, settings, output_transmit):
        import json, sys
        
        transmit_list = []
        start_delay = settings['start_delay']
        frame_spacing = settings['frame_spacing']
        max_frames = settings['max_frames']
        max_data_bytes = settings['max_data_bytes']
        
        frame_format_default = 0
        brs = 0
        if a2l_params["CAN_FD_DATA_TRANSFER_BAUDRATE"] != None and a2l_params["CAN_FD_DATA_TRANSFER_BAUDRATE"] != a2l_params["BAUDRATE"]:
            frame_format_default = 1
            brs = 1
        
        can_id_master = a2l_params['CAN_ID_MASTER'].replace("0x", "").upper()
        id_format = 1 if a2l_params['CAN_ID_MASTER_EXTENDED'] else 0
        
        delay = start_delay
        total_data_bytes = 0
        
        for frame in daq_frames:
            frame_format = 1 if len(frame['DATA']) > 16 else frame_format_default # More than 8 bytes means CAN FD
            frame_data_length = len(frame['DATA']) // 2  # Convert hex string length to bytes
            total_data_bytes += frame_data_length
            
            transmit_list.append({
                "name": frame["Name"],
                "state": 1,
                "id_format": id_format,
                "frame_format": frame_format,
                "brs": brs,
                "log": 1,
                "period": 0,
                "delay": delay,
                "id": can_id_master,
                "data": frame["DATA"]
            })
            
            delay += frame_spacing
        
        # Check for CANedge device limitations
        if len(transmit_list) > max_frames:
            print(f"WARNING: Transmit list contains {len(transmit_list)} frames, exceeding the limit of {max_frames} frames  - exiting script!")
            sys.exit()
        
        if total_data_bytes > max_data_bytes:
            print(f"WARNING: Total data bytes used: {total_data_bytes}, exceeding the limit of {max_data_bytes} bytes - exiting script!")
            sys.exit()
                
        transmit_list_json = json.dumps({"can_1": {"transmit": transmit_list}}, indent=2)
        
        # Save the transmit list JSON file
        output_transmit = output_transmit.with_suffix(".json")
        output_transmit.parent.mkdir(parents=True, exist_ok=True)
        with open(output_transmit, "w") as f:
            f.write(transmit_list_json)

        
        print(f"Created CANedge transmit list JSON with {len(transmit_list)} frames: {output_transmit}")
        
        return transmit_list_json

    # ----------------------------------
    # function for creating a status CSV file showing matched vs unmatched signals
    def create_status_csv(self, user_signals):
        import csv
        from pathlib import Path
        
        # Create output path based on input file name
        input_path = Path(self.signal_file)
        status_path = input_path.parent / f"{input_path.stem}_status.csv"
        
        # Prepare data rows - each row will have signal name and match status
        rows = []
        
        # Add unmatched signals first
        for signal_name in user_signals.keys():
            if signal_name not in self.matched_signals:
                rows.append([signal_name, user_signals[signal_name], "Not Matched"])
        
        # Then add matched signals
        for signal_name in user_signals.keys():
            if signal_name in self.matched_signals:
                rows.append([signal_name, user_signals[signal_name], "Matched"])
        
        # Write to CSV file
        with open(status_path, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.writer(csvfile, delimiter=';')
            writer.writerow(["Signal Name", "Event Channel", "Match Status"])  # Header
            writer.writerows(rows)
            
        print(f"\nCreated status CSV file: {status_path}")
        return status_path
        
    # ----------------------------------
    # function for creating DBC file from A2L signal information and DAQ frames
    def create_dbc(self, signals_grouped, a2l_params, output_dbc, settings): 
        dbc_content = [
            'VERSION "XCP_DBC"\n',
            'NS_ :',
            '\tNS_DESC_', '\tCM_', '\tBA_DEF_', '\tBA_', '\tVAL_', '\tCAT_DEF_',
            '\tCAT_', '\tFILTER', '\tBA_DEF_DEF_', '\tEV_DATA_', '\tENVVAR_DATA_',
            '\tSGTYPE_', '\tSGTYPE_VAL_', '\tBA_DEF_SGTYPE_', '\tBA_SGTYPE_',
            '\tSIG_TYPE_REF_', '\tVAL_TABLE_', '\tSIG_GROUP_', '\tSIG_VALTYPE_',
            '\tSIGTYPE_VALTYPE_', '\tBO_TX_BU_', '\tBA_DEF_REL_', '\tBA_REL_',
            '\tBA_DEF_DEF_REL_', '\tBU_SG_REL_', '\tBU_EV_REL_', '\tBU_BO_REL_', '\tSG_MUL_VAL_',
            '\nBS_:', '\nBU_: Logger\n'
        ]
        
        byte_order_flag = '1' if a2l_params['BYTE_ORDER'] == 'little' else '0'
        can_id_slave = int(a2l_params['CAN_ID_SLAVE'], 16)
        
        # Handle Classical vs. CAN FD fields
        dlc = 8
        bus_type = "CAN"
        if int(a2l_params['MAX_CTO'], 16) > 8 or int(a2l_params['MAX_DTO'], 16) > 8: 
            dlc = 64 
            bus_type ="CAN FD"
        
        # Handle vFrameFormat 
        vframeformat = "StandardCAN"
        if dlc == 8 and a2l_params['CAN_ID_SLAVE_EXTENDED'] == True: 
            vframeformat = "ExtendedCAN"
        if dlc == 64 and a2l_params['CAN_ID_SLAVE_EXTENDED'] == False: 
            vframeformat = "StandardCAN_FD"  
        if dlc == 64 and a2l_params['CAN_ID_SLAVE_EXTENDED'] == True: 
            vframeformat = "ExtendedCAN_FD"            
        
        
        # DTO Message Definition            
        dbc_content.append(f'BO_ {can_id_slave} DTO: {dlc} Logger')
        dbc_content.append('  SG_ DTOPID M : 0|8@1+ (1,0) [0|255] ""  Logger')

        pid_counter = 0
        signal_name_map = {}  # Track signal names for uniqueness
        signal_comments = []  # Store signal comments
        signal_floats = []    # Store signal float meta data

        for daq_list in sorted(set(signal['DAQ_LIST_NUMBER'] for signal in signals_grouped)):
            odts = sorted(set(signal['ODT_NUMBER'] for signal in signals_grouped if signal['DAQ_LIST_NUMBER'] == daq_list))
            for odt in odts:
                odt_signals = [s for s in signals_grouped if s['DAQ_LIST_NUMBER'] == daq_list and s['ODT_NUMBER'] == odt]
                bit_start = 8  # Start after PID (1st byte)
                for signal in odt_signals:
                    original_signal_name = signal['Name']
                    dbc_signal_name = original_signal_name.replace('.', '_')  # Convert "." to "_" for DBC compatibility
                    bit_length = signal['Length'] * 8
                    sign = '+' if signal['Signage'] == 'unsigned' else '-'
                    lower_limit = signal['LowerLimit']
                    upper_limit = signal['UpperLimit']
                    scale = signal['Scale']
                    offset = signal['Offset']
                    unit = signal['Unit']
                    long_identifier = signal.get('LongIdentifier', '').strip('"')

                    # Handle signal name shortening and uniqueness
                    if settings.get("shorten_signals", False):
                        base_name = dbc_signal_name[:29]  # First 29 characters
                        if base_name not in signal_name_map:
                            new_signal_name = base_name  # Use directly if unique
                        else:
                            suffix = 0
                            new_signal_name = f"{base_name}_{suffix:02d}"
                            while new_signal_name in signal_name_map:
                                suffix += 1
                                new_signal_name = f"{base_name}_{suffix:02d}"
                        signal_name_map[new_signal_name] = dbc_signal_name
                    else:
                        new_signal_name = dbc_signal_name

                    dbc_content.append(
                        f'  SG_ {new_signal_name} m{pid_counter} : {bit_start}|{bit_length}@{byte_order_flag}{sign} ({scale},{offset}) [{lower_limit}|{upper_limit}] "{unit}"  Logger'
                    )
                    
                    # Store signal comment (to be added in the next section)
                    comment_text = f'{original_signal_name} | {long_identifier}'
                    signal_comments.append(f'CM_ SG_ {can_id_slave} {new_signal_name} "{comment_text}";')
                    
                    # Add float/double meta data
                    if signal['Signage'] == "float":
                        signal_floats.append(f'SIG_VALTYPE_ {can_id_slave} {new_signal_name} : 1;')
                    if signal['Signage'] == "double":
                        signal_floats.append(f'SIG_VALTYPE_ {can_id_slave} {new_signal_name} : 2;')
                    
                    bit_start += bit_length
                pid_counter += 1

        # Insert all signal comments before the static meta section
        dbc_content.append("\n")
        dbc_content.extend(signal_comments)
        dbc_content.append("\n")

        # Meta section
        dbc_content.extend([
            'BA_DEF_ "BusType" STRING ;',
            'BA_DEF_ "ProtocolType" STRING ;',
            'BA_DEF_ SG_ "SystemSignalLongSymbol" STRING ;',
            'BA_DEF_ BO_ "VFrameFormat" ENUM "StandardCAN","ExtendedCAN","reserved","reserved","reserved","reserved","reserved","reserved","reserved","reserved","reserved","reserved","reserved","reserved","StandardCAN_FD","ExtendedCAN_FD";',
            'BA_DEF_ BO_ "MessageIgnore" INT 0 1;',
            'BA_DEF_ SG_ "SignalIgnore" INT 0 1;',
            'BA_DEF_DEF_ "BusType" "";',
            'BA_DEF_DEF_ "ProtocolType" "";',
            f'BA_DEF_DEF_ "VFrameFormat" "{vframeformat}";',
            'BA_DEF_DEF_ "MessageIgnore" 0;',
            'BA_DEF_DEF_ "SignalIgnore" 0;',
            'BA_DEF_DEF_ "SystemSignalLongSymbol" "";',
            f'BA_ "BusType" "{bus_type}";',
            'BA_ "ProtocolType" "";',
        ])

        # Add "SignalIgnore" for DTOPID message (for use in MF4 decoders)
        dbc_content.append(f'BA_ "SignalIgnore" SG_ {can_id_slave} DTOPID 1;')
        
        # Add signal float section (if any)
        if len(signal_floats):
            dbc_content.append("\n")
            dbc_content.extend(signal_floats)
            dbc_content.append("\n")

        output_dbc = output_dbc.with_suffix(".dbc")
        output_dbc.parent.mkdir(parents=True, exist_ok=True)
        with open(output_dbc, "w") as f:
            f.write("\n".join(dbc_content))
        
        print(f"Created DBC file: {output_dbc}")
        return output_dbc
