#!/usr/bin/python

from collections import defaultdict
import sys
import os


class MemAreaType:
    values = ['normal', 'stack', 'heap', 'mapped_file', 'vdso']
    NORMAL = values[0]
    STACK = values[1]
    HEAP = values[2]
    MAPPED_FILE = values[3]
    VDSO = values[4]


class PDump:

    def __init__(self, f):
        self.memory_areas = {MemArea(line) for line in f}
        self.memory_areas_by_type = defaultdict(set)

        for ma in self.memory_areas:
            self.memory_areas_by_type[ma.type].add(ma)

    def summerize(self):
        print "Process address space has %d memory areas mapped" % len(self.memory_areas)
        self._summerize(self.memory_areas)
        print ""

        readable_memory_areas = {ma for ma in self.memory_areas if ma.is_readable}
        print "%d memory areas are readable" % len(readable_memory_areas)
        self._summerize(readable_memory_areas)
        print ""

        writeable_memory_areas = {ma for ma in self.memory_areas if ma.is_writable}
        print "%d memory areas are writeable" % len(writeable_memory_areas)
        self._summerize(writeable_memory_areas)
        print ""

        executable_memory_areas = {ma for ma in self.memory_areas if ma.is_executable}
        print "%d memory areas are executable" % len(executable_memory_areas)
        self._summerize(executable_memory_areas)
        print ""

    def _summerize(self, memory_areas_to_summerize):
        print "TYPE".rjust(12), "COUNT".rjust(8), "SIZE (kb)".rjust(12)
        for mem_area_type in MemAreaType.values:
            memory_areas = memory_areas_to_summerize & self.memory_areas_by_type[mem_area_type]
            print mem_area_type.rjust(12), 
            print str(len(memory_areas)).rjust(8),
            print str(sum(ma.kb for ma in memory_areas)).rjust(12)
        print "total".rjust(12), 
        print str(len(memory_areas_to_summerize)).rjust(8),
        print str(sum(ma.kb for ma in memory_areas_to_summerize)).rjust(12)


class MemArea:
    """A memory area from a usermode processes's process address space"""

    def __init__(self, line):
        """Extract structured information about a memory from a line of thread_id
        /proc/<pid>/maps file
        """
        self.line = line
        try:
            address_range, permissions, offset, device, inode, pathname = line.split()
        except ValueError:
            address_range, permissions, offset, device, inode = line.split()
            pathname = None
        self.address_range = address_range
        start_address_hex, end_address_hex = address_range.split('-')
        self.start_address = int(start_address_hex,16)
        self.end_address = int(end_address_hex,16)
        self.kb = (self.end_address - self.start_address) / 1024
        self.permissions = permissions
        self.is_readable = 'r' in permissions
        self.is_writable = 'w' in permissions
        self.is_executable = 'x' in permissions
        self.is_private = 'p' in permissions
        self.offset = offset
        self.device = device
        self.inode = inode
        self.is_stack = False
        self.thread_id = None
        self.is_heap = False
        self.is_vdso = False
        self.file_path = None
        self.type = MemAreaType.NORMAL

        if pathname is not None:
            if pathname.startswith('/'):
                self.file_path = pathname
                self.type = MemAreaType.MAPPED_FILE
            elif 'heap' in pathname:
                self.is_heap = True
                self.type = MemAreaType.HEAP
            elif 'stack' in pathname:
                self.is_stack = True
                self.type = MemAreaType.STACK
                split = pathname.strip('[]').split(':')
                if len(split) == 2:
                    self.thread_id = int(split[1])
            elif 'vdso' in pathname:
                self.is_vdso = True
                self.type = MemAreaType.VDSO

    def __str__(self):
        return "address_range: {}, size (kb): {}, permissions: {}, type: {}".format(self.address_range, self.kb, self.permissions, self.type)

    def __repr__(self):
        return 'MemArea("{}")'.format(self.line.strip())


class MemoryAreaPart:

    def __init__(self, memory_area, start_address=None, end_address=None):
        self.memory_area = memory_area
        if start_address is None:
            self.start_address = memory_area.start_address
        else:
            self.start_address = start_address 

        if end_address is None:
            self.end_address = memory_area.end_address
        else:
            self.end_address = end_address 

        self.address_range = "{}-{}".format(hex(self.start_address), hex(self.end_address))
        self.kb = (self.end_address - self.start_address) / 1024

    def __str__(self):
        return "address_range: {}, size (kb): {}, permissions: {}, type: {}".format(self.address_range, self.kb, self.memory_area.permissions, self.memory_area.type)

    def __repr__(self):
        return 'MemoryAreaPart({}, {}, {})'.format(repr(self.memory_area), self.start_address, self.end_address)


def diff(earlier_mas, later_mas):
    added_parts = []
    removed_parts = []

    # sort by start address
    key_func = lambda ma: ma.start_address
    earlier = sorted(list(earlier_mas), key=key_func)
    later = sorted(list(later_mas), key=key_func)

    ei = 0
    li = 0

    try:
        ema = MemoryAreaPart(earlier[ei])
        lma = MemoryAreaPart(later[li])


        while True:
            if ema.end_address < lma.start_address:
                # whole area was removed
                removed_parts.append(ema)
                ei += 1
                ema = MemoryAreaPart(earlier[ei])
            elif lma.end_address < ema.start_address:
                # whole area was added
                added_parts.append(lma)
                li += 1
                lma = MemoryAreaPart(later[li])
            else:
                # areas overlap
                if ema.start_address < lma.start_address:
                    # segment was removed
                    removed_parts.append(MemoryAreaPart(ema.memory_area, ema.start_address, lma.start_address))
                    if ema.end_address < lma.end_address:
                        lma = MemoryAreaPart(lma.memory_area, ema.end_address, lma.end_address)
                        ei += 1
                        ema = MemoryAreaPart(earlier[ei])
                    elif ema.end_address > lma.end_address:
                        ema = MemoryAreaPart(ema.memory_area, lma.end_address, ema.end_address)
                        li += 1
                        lma = MemoryAreaPart(later[li])
                    else:
                        ei += 1
                        li += 1
                        ema = MemoryAreaPart(earlier[ei])
                        lma = MemoryAreaPart(later[li])
                elif ema.start_address > lma.start_address:
                    # segment was added
                    added_parts.append(MemoryAreaPart(lma.memory_area, lma.start_address, ema.start_address))
                    if ema.end_address > lma.end_address:
                        ema = MemoryAreaPart(ema.memory_area, lma.end_address, ema.end_address)
                        li += 1
                        lma = MemoryAreaPart(later[li])
                    elif ema.end_address < lma.end_address:
                        lma = MemoryAreaPart(lma.memory_area, ema.end_address, lma.end_address)
                        ei += 1
                        ema = MemoryAreaPart(earlier[ei])
                    else:
                        li += 1
                        ei += 1
                        lma = MemoryAreaPart(later[li])
                        ema = MemoryAreaPart(earlier[ei])
                else:
                    # segments start in the same place, just advance
                    if ema.end_address < lma.end_address:
                        lma = MemoryAreaPart(lma.memory_area, ema.end_address, lma.end_address)
                        ei += 1
                        ema = MemoryAreaPart(earlier[ei])
                    elif ema.end_address > lma.end_address:
                        ema = MemoryAreaPart(ema.memory_area, lma.end_address, ema.end_address)
                        li += 1
                        lma = MemoryAreaPart(later[li])
                    else:
                        ei += 1
                        li += 1
                        ema = MemoryAreaPart(earlier[ei])
                        lma = MemoryAreaPart(later[li])
    except IndexError:
        # done with at least one of the lists
        if ei < len(earlier):
            removed_parts.append(ema)
            for i in range(ei + 1, len(earlier)):
                removed_parts.append(MemoryAreaPart(earlier[i]))
        if li < len(later):
            added_parts.append(lma)
            for i in range(li + 1, len(later)):
                added_parts.append(MemoryAreaPart(later[i]))

    return removed_parts, added_parts


if __name__ == "__main__":
    name = sys.argv[0]
    if len(sys.argv) == 2:
        input_filepath = sys.argv[1]
        with open(input_filepath) as input_file:
            pd = PDump(input_file)
            print "+++++ Memory Areas Sorted By Size +++++"
            print '\n'.join(str(ma) for ma in reversed(sorted(pd.memory_areas, key=lambda x: x.kb)))
            pd.summerize()
    elif len(sys.argv) == 3:
        input_filepath1 = sys.argv[1]
        input_filepath2 = sys.argv[2]
        with open(input_filepath1) as f1, open(input_filepath2) as f2:
            pd1 = PDump(f1)
            pd2 = PDump(f2)
            removed, added = diff(pd1.memory_areas, pd2.memory_areas)
            removed_kb = sum(r.kb for r in removed)
            added_kb = sum(a.kb for a in added)
            print "The total size of this process's memory areas changed by {} kb".format(str(added_kb - removed_kb))
            print "Removed {} kb:".format(str(removed_kb))
            print '\n'.join(str(r) for r in removed)
            print "Added {} kb:".format(str(added_kb))
            print '\n'.join(str(a) for a in added)
            print ""
            print "Breakdown by type"
            for t in MemAreaType.values:
                print "===== {} Memory Areas =====".format(t)
                removed, added = diff(pd1.memory_areas_by_type[t], pd2.memory_areas_by_type[t])
                removed_kb = sum(r.kb for r in removed)
                added_kb = sum(a.kb for a in added)
                print "Net change: {} kb".format(str(added_kb - removed_kb))
                print "Removed {} kb:".format(str(removed_kb))
                print '\n'.join(str(r) for r in removed)
                print "Added {} kb:".format(str(added_kb))
                print '\n'.join(str(a) for a in added)
