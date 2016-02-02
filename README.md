# mem-insights
Utils for analyzing processes memory usage on linux systems

## REQUIREMENTS
- Python 2.7

## MODULES
### pdump.py
To analyze the process address space of a running process
```bash
cat /proc/[pid]/maps > process.dump
./pdump.py process.dump
```

To find the changes in the process address space over some time period
```bash
cat /proc/[pid]/maps > <timestamp1>.dump
cat /proc/[pid]/maps > <timestamp2>.dump
./pdump.py <timestamp1>.dump <timestamp2>.dump
```

Can also be used as a python module. For example
$ python
```python
import pdump                # folder must be added to python path for this to work
f = open("process.dump")
pd = pdump.PDump(f)
private_file_memory_areas = (ma for ma in pd.memory_areas_by_type[pdump.MemAreaType.MAPPED_FILE] if ma.is_private)
print "\n".join("{} | {}".format(str(ma), ma.file_path) for ma in private_file_memory_areas)
```
--------------------------------------------------------------------------------
