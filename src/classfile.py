"""Read the constant pool and binary fields of the reviewed JVM class."""

import struct


class Reader:
    def __init__(self, data):
        self.data = data
        self.pos = 0

    def take(self, size):
        value = self.data[self.pos:self.pos + size]
        if len(value) != size:
            raise ValueError('Truncated JVM class')
        self.pos += size
        return value

    def number(self, size):
        return int.from_bytes(self.take(size), 'big')


def index_bytes(*indices):
    return struct.pack('>' + 'H' * len(indices), *indices)


class ConstantPool:
    def __init__(self, reader):
        count = reader.number(2)
        self.entries = [None] * count
        index = 1
        while index < count:
            start = reader.pos
            tag = reader.number(1)
            if tag == 1:
                reader.take(reader.number(2))
            elif tag in (3, 4, 9, 10, 11, 12):
                reader.take(4)
            elif tag in (5, 6):
                reader.take(8)
            elif tag in (7, 8):
                reader.take(2)
            else:
                raise ValueError('Unrecognized JVM constant pool tag')
            self.entries[index] = reader.data[start:reader.pos]
            index += 2 if tag in (5, 6) else 1

    def add(self, tag, data):
        entry = bytes([tag]) + data
        if entry in self.entries:
            return self.entries.index(entry)
        self.entries.append(entry)
        return len(self.entries) - 1

    def utf(self, value):
        text = value.encode('ascii')
        return self.add(1, index_bytes(len(text)) + text)

    def is_utf(self, index, value):
        return self.entries[index][3:] == value.encode('ascii') and self.entries[index][0] == 1

    def class_id(self, name):
        return self.add(7, index_bytes(self.utf(name)))

    def encode(self):
        return index_bytes(len(self.entries)) + b''.join(entry for entry in self.entries if entry)
