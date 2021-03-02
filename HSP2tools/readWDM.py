''' Copyright (c) 2020 by RESPEC, INC.
Author: Robert Heaphy, Ph.D.

Based on MATLAB program by Seth Kenner, RESPEC
License: LGPL2
'''

import numpy as np
import pandas as pd
from numba import jit
import datetime
from dateutil.relativedelta import relativedelta
import timeit


# look up attributes NAME, data type (Integer; Real; String) and data length by attribute number
attrinfo = {1:('TSTYPE','S',4),     2:('STAID','S',16),    11:('DAREA','R',1),
           17:('TCODE','I',1),     27:('TSBYR','I',1),     28:('TSBMO','I',1),
           29:('TSBDY','I',1),     30:('TSBHR','I',1),     32:('TFILL', 'R',1),
           33:('TSSTEP','I',1),    34:('TGROUP','I',1),    45:('STNAM','S',48),
           83:('COMPFG','I',1),    84:('TSFORM','I',1),    85:('VBTIME','I',1),
          444:('DATMOD','S',12),  443:('DATCRE','S',12),   22:('DCODE','I',1),
           10:('DESCRP','S', 80),   7:('ELEV','R',1),       8:('LATDEG','R',1),
            9:('LNGDEG','R',1),   288:('SCENARIO','S',8), 289:('CONSTITUENT','S',8),
          290:('LOCATION','S',8)}

freq = {7:'100YS', 6:'YS', 5:'MS', 4:'D', 3:'H', 2:'min', 1:'S'}   # pandas date_range() frequency by TCODE, TGROUP



def readWDM(wdmfile, hdffile, jupyterlab=True):
    iarray = np.fromfile(wdmfile, dtype=np.int32)
    farray = np.fromfile(wdmfile, dtype=np.float32)

    if iarray[0] != -998:
        print('Not a WDM file, magic number is not -990. Stopping!')
        return
    nrecords    = iarray[28]    # first record is File Definition Record
    ntimeseries = iarray[31]

    dsnlist = []
    for index in range(512, nrecords * 512, 512):
        if not (iarray[index]==0 and iarray[index+1]==0 and iarray[index+2]==0 and iarray[index+3]==0) and iarray[index+5]==1:
            dsnlist.append(index)
    if len(dsnlist) != ntimeseries:
        print('PROGRAM ERROR, wrong number of DSN records found')

    with pd.HDFStore(hdffile) as store:
        summary = []
        summaryindx = []

        # check to see which extra attributes are on each dsn
        columns_to_add = []
        search = ['STAID', 'STNAM', 'SCENARIO', 'CONSTITUENT', 'LOCATION']
        for att in search:
            found_in_all = True
            for index in dsnlist:
                dattr = {}
                psa = iarray[index + 9]
                if psa > 0:
                    sacnt = iarray[index + psa - 1]
                for i in range(psa + 1, psa + 1 + 2 * sacnt, 2):
                    id = iarray[index + i]
                    ptr = iarray[index + i + 1] - 1 + index
                    if id not in attrinfo:
                        continue
                    name, atype, length = attrinfo[id]
                    if atype == 'I':
                        dattr[name] = iarray[ptr]
                    elif atype == 'R':
                        dattr[name] = farray[ptr]
                    else:
                        dattr[name] = ''.join([itostr(iarray[k]) for k in range(ptr, ptr + length // 4)]).strip()
                if att not in dattr:
                    found_in_all = False
            if found_in_all:
                columns_to_add.append(att)

        for index in dsnlist:
            # get layout information for TimeSeries Dataset frame
            dsn   = iarray[index+4]
            psa   = iarray[index+9]
            if psa > 0:
                sacnt = iarray[index+psa-1]
            pdat  = iarray[index+10]
            pdatv = iarray[index+11]
            frepos = iarray[index+pdat]

            print(f'{dsn} reading from wdm')
            # get attributes
            dattr = {'TSBDY':1, 'TSBHR':1, 'TSBMO':1, 'TSBYR':1900, 'TFILL':-999.}   # preset defaults
            for i in range(psa+1, psa+1 + 2*sacnt, 2):
                id = iarray[index + i]
                ptr = iarray[index + i + 1] - 1 + index
                if id not in attrinfo:
                    # print('PROGRAM ERROR: ATTRIBUTE INDEX not found', id, 'Attribute pointer', iarray[index + i+1])
                    continue

                name, atype, length = attrinfo[id]
                if atype == 'I':
                    dattr[name] = iarray[ptr]
                elif atype == 'R':
                    dattr[name] = farray[ptr]
                else:
                    dattr[name] = ''.join([itostr(iarray[k]) for k in range(ptr, ptr + length//4)]).strip()

            # Get timeseries timebase data
            groups = [] #renaming to groups to be consistent with WDM documentation
            for i in range(pdat+1, pdatv-1):
                a = iarray[index+i]
                if a != 0:
                    groups.append(splitposition(a))
            if len(groups) == 0:
                continue   # WDM preallocation, but nothing saved here yet

            srec, soffset = groups[0]
            start = splitdate(iarray[srec*512 + soffset])

            sprec, spoffset = splitposition(frepos)
            finalindex = sprec * 512 + spoffset

            # calculate number of data points in each group, tindex is final index for storage
            tgroup = dattr['TGROUP']
            tstep  = dattr['TSSTEP']
            tcode  = dattr['TCODE']

            #PRT - this code was done to preallocate a numpy array, however WDM file can contain timeseries with irregular timesteps
            #so calculating a single steps and preallocating a nparray will lead to issues. 
            cindex = pd.date_range(start=start, periods=len(groups)+1, freq=freq[tgroup])
            tindex = pd.date_range(start=start, end=cindex[-1], freq=str(tstep) + freq[tcode])
            counts = np.diff(np.searchsorted(tindex, cindex))

            ## Get timeseries data
            #floats = np.zeros(sum(counts),  dtype=np.float32)
            #findex = 0
            #for (rec,offset),count in zip(groups, counts):
                #findex = getfloats(iarray, farray, floats, findex, rec, offset, count, finalindex, tcode, tstep)
            
            #replaced with group/block processing approach
            dates, values = process_groups(iarray, farray, groups, tgroup)

            ## Write to HDF5 file
            series = pd.Series(values, index=dates)
            dsname = f'TIMESERIES/TS{dsn:03d}'
            # series.to_hdf(store, dsname, complib='blosc', complevel=9)
            if jupyterlab:
                series.to_hdf(store, dsname, complib='blosc', complevel=9)  # This is the official version
            else:
                series.to_hdf(store, dsname, format='t', data_columns=True)  # show the columns in HDFView

            data = [str(tindex[0]), str(tindex[-1]), str(tstep) + freq[tcode],
            len(series),  dattr['TSTYPE'], dattr['TFILL']]
            columns = ['Start', 'Stop', 'Freq','Length', 'TSTYPE', 'TFILL']
            # search = ['STAID', 'STNAM', 'SCENARIO', 'CONSTITUENT','LOCATION']
            for x in columns_to_add:
                if x in dattr:
                    data.append(dattr[x])
                    columns.append(x)

            summary.append(data)
            summaryindx.append(dsname[11:])


        dfsummary = pd.DataFrame(summary, index=summaryindx, columns=columns)
        store.put('TIMESERIES/SUMMARY',dfsummary, format='t', data_columns=True)
    return dfsummary


def todatetime(yr=1900, mo=1, dy=1, hr=0):
    '''takes yr,mo,dy,hr information then returns its datetime64'''
    if hr == 24:
        return datetime.datetime(yr, mo, dy, 23) + pd.Timedelta(1,'h')
    else:
        return datetime.datetime(yr, mo, dy, hr)

def splitdate(x):
    '''splits WDM int32 DATWRD into year, month, day, hour -> then returns its datetime64'''
    return todatetime(x >> 14, x >> 10 & 0xF, x >> 5 & 0x1F, x & 0x1F) # args: year, month, day, hour

def splitcontrol(x):
    ''' splits int32 into (qual, compcode, units, tstep, nvalues)'''
    return(x & 0x1F, x >> 5 & 0x3, x >> 7 & 0x7, x >> 10 & 0x3F, x >> 16)

def splitposition(x):
    ''' splits int32 into (record, offset), converting to Pyton zero based indexing'''
    return((x>>9) - 1, (x&0x1FF) - 1)

def itostr(i):
    return chr(i & 0xFF) + chr(i>>8 & 0xFF) + chr(i>>16 & 0xFF) + chr(i>>24 & 0xFF)

# @jit(nopython=True, cache=True)
def leap_year(y):
    if y % 400 == 0:
        return True
    if y % 100 == 0:
        return False
    if y % 4 == 0:
        return True
    else:
        return False

def deltaTime(ltstep, ltcode):
    deltaT = relativedelta(
        years= ltstep if ltcode == 6 else 0, #if need to support 100yrs modify this line
        months= ltstep if ltcode == 5 else 0,
        days= ltstep if ltcode == 4 else 0,
        hours= ltstep if ltcode == 3 else 0,
        minutes= ltstep if ltcode == 2 else 0,
        seconds= ltstep if ltcode == 1 else 0)
    return deltaT

# HTAO - an alternative implementation of process_group:
# 1. used lists to replace numpy matrix;
# 2. added a loop to iterate each group and used ending date as the ending condition
def process_groups(iarray, farray, groups, tgroup):

    date_array = []
    value_array = []

    for record, offset in groups:
        index = record * 512 + offset
        pscfwr = iarray[record * 512 + 3] #should be 0 for last record in timeseries 
        current_date = splitdate(iarray[index])
        lGroupEndDate = current_date + deltaTime(1, tgroup)
        offset +=1
        index +=1

        while current_date < lGroupEndDate:
            #read block control word
            x = iarray[index]  # block control word or maybe date word at start of group
            nval = x >> 16
            ltstep = int(x >> 10 & 0x3f) #relative_delta doesn't handle numpy.32bitInt correctly so convert to python
            ltcode = int(x >> 7 & 0x7)
            comp = x >> 5 & 0x3
            qual  = x & 0x1f
            deltaT = deltaTime(ltstep, ltcode)
            #check if next block will exceed array size and allocate additional chunk if needed 
            #if nval + array_index >= value_array.shape[0]:
            #    date_array = np.concatenate((date_array, np.zeros(array_chunk_size, dtype='M8[us]')))
            #    value_array = np.concatenate((value_array, np.zeros(array_chunk_size, dtype=np.float32)))

            #compressed - only has single value which applies to full range
            if comp == 1:
                #TODO -  verfiy we do not need support for code 7 or 100YRS? this is in freq but not the programmers documentation
                for i in range(0, nval, 1):
                    current_date = current_date + deltaT
                    date_array.append(current_date)
                    value_array.append(farray[index + 1])
                index += 2
                offset +=2
            #not compressed - read nval from floats (number of values)
            else:
                for i in range(0, nval, 1):
                    current_date = current_date + deltaT
                    date_array.append(current_date)
                    value_array.append(farray[index + 1 + i])
                index += 1 + nval
                offset +=1 + nval
            
            if offset >= 512:
                #print("offset:", str(offset))
                offset = 4
                index = (pscfwr - 1) * 512 + offset
                record = pscfwr
                #pscbkr = iarray[(record - 1) * 512 + 2] #should always be 0 for first record in timeseries
                pscfwr = iarray[(record - 1) * 512 + 3] #should be 0 for last record in timeseries

    #df = pd.DataFrame({'date':date_array, 'values':value_array})
    #df.to_csv(R'C:\users\ptomasula\desktop\debugging.csv')
    return date_array, value_array
