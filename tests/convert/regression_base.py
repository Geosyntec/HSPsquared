import os
import inspect
import webbrowser
from HSP2tools.readWDM import get_wdm_data_set
from HSP2tools.HBNOutput import HBNOutput
from HSP2tools.HDF5 import HDF5
import pandas as pd
import numpy as np


class RegressTestBase(object):
    def __init__(self):
        self.test_dir = ''
        self.test_meta = {}
        self.compare_tcodes = [2]  # control time unit for comparison
        # self.compare_cases = ['test05', 'test09', 'test10', 'test10b', 'Calleg', 'GRW_Plaster', 'ZRW_WestIndian']
        self.compare_cases = ['test10']  # control test cases for comparison

    def run_one_test_wdm(self, testdir):
        attributes = {'location': 'unk', 'dsn': 39, 'constituent': 'PREC'}
        filename = ''
        df = get_wdm_data_set(filename, attributes)
        x = []
        y = []

    def get_hbn_data(self, test_dir):
        sub_dirs = os.listdir(test_dir)
        hbn_files = []
        for sub_dir in sub_dirs:
            if sub_dir.__contains__('HSPFresults'):
                files = os.listdir(os.path.join(test_dir, sub_dir))
                for file in files:
                    if file.lower().endswith('.hbn'):
                        hbn_files.append(os.path.join(test_dir, sub_dir, file))
                break

        if len(hbn_files) == 0:
            return []

        hbn_data = []
        for hbn_file_name in hbn_files:
            hbn_output = HBNOutput(hbn_file_name)
            hbn_output.read_data()
            # tser = hbn_output.get_time_series('SOQUALCOD', 'hourly')
            # HBNOutput.save_time_series_to_file(os.path.join(os.path.split(hbn_output.file_name)[0], 'zhbn.txt'), tser)
            hbn_data.append(hbn_output)

        return hbn_data

    def get_hdf5_data(self, test_dir):
        sub_dirs = os.listdir(test_dir)
        h5_files = []
        for sub_dir in sub_dirs:
            if sub_dir.__contains__('HSP2results'):
                files = os.listdir(os.path.join(test_dir, sub_dir))
                for file in files:
                    if file.lower().endswith('.h5') or file.lower().endswith('.hdf'):
                        h5_files.append(os.path.join(test_dir, sub_dir, file))
                break

        if len(h5_files) == 0:
            return []

        h5_data = []
        for h5_file_name in h5_files:
            h5_output = HDF5(h5_file_name)
            # h5_output.read_output()
            h5_output.open_output()
            h5_output.read_output('IMPLND')
            # tser = h5_output.get_time_series('SOQUALCOD', 'hourly')
            # HBNOutput.save_time_series_to_file(os.path.join(os.path.split(h5_output.file_name)[0], 'zh5.txt'), tser)
            h5_data.append(h5_output)

        return h5_data

    def run_one_test(self, test_dir):
        # after getting the outputs from both hbn and hdf5
        #   compare them one at a time
        #   output comparison result in HTML format

        hbn_data = self.get_hbn_data(test_dir)
        hdf5_data = self.get_hdf5_data(test_dir)

        style_th = 'style="text-align:left"'
        style_header = 'style="border:1px solid; background-color:#EEEEEE"'
        html = '<table style="border:1px solid">\n'
        for hbn_dataset in hbn_data:
            for key in hbn_dataset.output_dictionary.keys():
                # key = f'{operation}_{activity}_{id:03d}_{tcode}'
                tcode = int(key[key.rindex('_')+1:])
                if tcode not in self.compare_tcodes:
                    # only compare hourly outputs
                    continue

                html += f'<tr><th colspan=5 {style_header}>{key}</th></tr>\n'
                html += f'<tr><th></th><th {style_th}>Constituent</th><th {style_th}>Max Diff</th><th>Match</th><th>Note</th></tr>\n'
                (operation, activity, opn_id, tcode) = key.split('_')
                for cons in hbn_dataset.output_dictionary[key]:
                    # get the operation type: IMPLND, PERLND, RCHRES
                    # get the operation id
                    # get the activity
                    # now with the 4 pieces of info, opn_type, opn_id, activity, and cons:
                    #   get single output time series from HBNOutput object
                    #   get single output time series from HDF5 object
                    #   compare and generate HTML report
                    hbn_time_series = hbn_dataset.get_time_series(operation, int(opn_id), cons, activity, 'hourly')
                    h5_time_series = hdf5_data[0].get_time_series(operation, int(opn_id), cons, activity)
                    # hbn_s = pd.Series(hbn_time_series.values)
                    # h5_s = pd.Series(h5_time_series.values)

                    if (activity == "PWTGAS" and (cons == "SOTMP" or cons == "SODOX" or cons == "SOCO2")):  # prepare for special exceptions
                        hbn_suro_time_series = hbn_dataset.get_time_series(operation, int(opn_id), "SURO", "PWATER", 'hourly')
                        h5_suro_time_series = hdf5_data[0].get_time_series(operation, int(opn_id), "SURO", "PWATER")
                    if (activity == "SEDTRN" and (cons == "SSEDCLAY" or cons == "SSEDTOT")):  # prepare for special exceptions
                        h5_vol_time_series = hdf5_data[0].get_time_series(operation, int(opn_id), "VOL", "HYDR")
                    missing_data_h5 = ''
                    missing_data_hbn = ''
                    if hbn_time_series is None:
                        missing_data_hbn = f'not in hbn'
                    if h5_time_series is None:
                        missing_data_h5 = f'not in h5'
                    #Special case, for some parameters (e.g PLANK.BENAL1) HSPF results look to be array.
                    #Working assumption is that only the first index of that array are the values of interest.
                    if len(hbn_time_series.shape) > 1:
                        hbn_time_series = hbn_time_series.iloc[:,0]

                    if len(missing_data_h5) > 0 or len(missing_data_hbn) > 0:
                        html += f'<tr><td>-</td><td>{cons}</td><td>NA</td><td>NA</td><td>{missing_data_h5}<br>{missing_data_hbn}</td></tr>\n'
                    else:
                        abstol = 1e-2
                        # In some test cases it looked like HSP2 was executing for a single extra time step 
                        # Trim h5 (HSP2) results to be same length as hbn (HSPF)
                        # This is a bandaid to get testing working. long term should identify why HSP2 runs for additional time step.
                        if len(h5_time_series) > len(hbn_time_series):
                            h5_time_series = h5_time_series[0:len(hbn_time_series)]
                       
                        ### special case here to catch cases that are not signficant differences but appear to be
                        for i in range(h5_time_series.values.size):
                            if np.isnan(h5_time_series.values[i]):
                                h5_time_series.values[i] = 0.0
                            if hbn_time_series.values[i] < -1.0e26:
                                hbn_time_series.values[i] = 0.0
                            if h5_time_series.values[i] < -1.0e26:
                                h5_time_series.values[i] = 0.0
                            # special exceptions
                            # if tiny suro in one and no suro in the other, don't trigger on suro-dependent numbers
                            if (activity == "PWTGAS" and (cons == "SOTMP" or cons == "SODOX" or cons == "SOCO2")):
                                if (h5_suro_time_series.values[i] == 0.0 and hbn_suro_time_series.values[i] < 1.0e-8) or \
                                    (hbn_suro_time_series.values[i] == 0.0 and h5_suro_time_series.values[i] < 1.0e-8):
                                    h5_time_series.values[i] = 0.0
                                    hbn_time_series.values[i] = 0.0
                            # if volume in reach is going to zero, small concentration differences are not signficant
                            if (activity == "SEDTRN" and (cons == "SSEDCLAY" or cons == "SSEDTOT")):
                                if h5_vol_time_series.values[i] < 1.0e-4:
                                    h5_time_series.values[i] = 0.0
                                    hbn_time_series.values[i] = 0.0
                        # if heat related term, compute special tolerance
                        if cons == 'IHEAT' or cons == 'ROHEAT' or cons.startswith('OHEAT') or \
                                cons == 'QSOLAR' or cons == 'QLONGW' or cons == 'QEVAP' or \
                                cons == 'QCON' or cons == 'QPREC' or cons == 'QBED':
                            abstol = max(abs(h5_time_series.values.min()), abs(h5_time_series.values.max())) * 1e-4
                        elif cons == 'QTOTAL' or cons == 'HTEXCH' :
                            abstol = max(abs(h5_time_series.values.min()), abs(h5_time_series.values.max())) * 1e-3
                        ### end special exception code here
                        max_diff1 = (hbn_time_series.values - h5_time_series.values).max()
                        max_diff2 = (h5_time_series.values - hbn_time_series.values).max()
                        max_diff = max(max_diff1, max_diff2)
                        match = False
                        if np.allclose(hbn_time_series, h5_time_series, rtol=1e-2, atol=abstol, equal_nan=False):
                            match = True
                        match_symbol = f'<span style="font-weight:bold;color:red">X</span>'
                        if match:
                            match_symbol = f'<span style="font-weight:bold;color:green">&#10003;</span>'

                        html += f'<tr><td>-</td><td>{cons}</td><td>{max_diff}</td><td>{match_symbol}</td><td></td></tr>\n'
                        pass

        html += f'</table>\n'

        return html

    def run_test(self):
        # find all tests
        current_directory = os.path.dirname(os.path.abspath(inspect.getframeinfo(inspect.currentframe()).filename))
        source_root_path = os.path.split(os.path.split(current_directory)[0])[0]
        test_path = os.path.join(source_root_path, "tests")

        html_file = os.path.join(test_path, 'test_report_conversion.html')
        text_file = open(html_file, "w")
        text_file.write('<html><header><h1>CONVERSION TEST REPORT</h1></header><body>\n')

        test_dirs = os.listdir(test_path)
        test_dirs_selected = []
        for test_dir in test_dirs:
            if test_dir in self.compare_cases:
                test_dirs_selected.append(test_dir)

        test_case_count = 1
        for test_dir in test_dirs_selected:
            if test_dir not in self.compare_cases:
                continue
            else:
                print(f'conversion test case: {test_dir} ({test_case_count} of {len(test_dirs_selected)})')
                text_file.write(f'<h3>{os.path.join(test_path, test_dir)}</h3>\n')
                one_test_report = self.run_one_test(os.path.join(test_path, test_dir))
                text_file.write(one_test_report)
            test_case_count += 1

        text_file.write("</body></html>\n")
        text_file.close()
        print('conversion tests are done.')

        try:
            webbrowser.open_new_tab('file://' + html_file)
        except:
            print("Error writing test results to " + html_file)
