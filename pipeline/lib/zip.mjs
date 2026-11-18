// A small zip reader and writer with no dependencies (DATA_CONVENTIONS section 18): enough to
// read one named file from the Board's H.6 release zip, and to write the fixture zips. A zip is
// untrusted data: sizes are bounded before anything is inflated, the CRC-32 is checked, and
// anything unusual (encryption, zip64, another compression method) is refused, never guessed.
import { crc32, deflateRawSync, inflateRawSync } from 'node:zlib';

const EOCD = 0x06054b50;
const CENTRAL = 0x02014b50;
const LOCAL = 0x04034b50;

/** The central directory entries of a zip: [{ name, method, flags, crc, compressedSize, size, offset }]. */
export function zipEntries(bytes) {
  if (!Buffer.isBuffer(bytes) || bytes.length < 22) throw new RangeError('zip: too short');
  // The end record is within the last 64 KiB plus its own 22 bytes.
  let at = -1;
  for (let i = bytes.length - 22; i >= Math.max(0, bytes.length - 22 - 65535); i -= 1) {
    if (bytes.readUInt32LE(i) === EOCD) {
      at = i;
      break;
    }
  }
  if (at < 0) throw new RangeError('zip: no end of central directory record');
  const count = bytes.readUInt16LE(at + 10);
  const size = bytes.readUInt32LE(at + 12);
  const start = bytes.readUInt32LE(at + 16);
  if (count === 0xffff || start === 0xffffffff) throw new RangeError('zip: zip64 is not supported');
  if (start + size > at) throw new RangeError('zip: the central directory overlaps the end record');
  const entries = [];
  let p = start;
  for (let i = 0; i < count; i += 1) {
    if (p + 46 > bytes.length || bytes.readUInt32LE(p) !== CENTRAL) throw new RangeError('zip: bad central directory entry');
    const nameLength = bytes.readUInt16LE(p + 28);
    const extraLength = bytes.readUInt16LE(p + 30);
    const commentLength = bytes.readUInt16LE(p + 32);
    entries.push({
      name: bytes.subarray(p + 46, p + 46 + nameLength).toString('utf8'),
      flags: bytes.readUInt16LE(p + 8),
      method: bytes.readUInt16LE(p + 10),
      crc: bytes.readUInt32LE(p + 16),
      compressedSize: bytes.readUInt32LE(p + 20),
      size: bytes.readUInt32LE(p + 24),
      offset: bytes.readUInt32LE(p + 42),
    });
    p += 46 + nameLength + extraLength + commentLength;
  }
  return entries;
}

/**
 * The bytes of one named file. `maxBytes` bounds the uncompressed size before inflating; the
 * result is checked against the stated size and CRC-32.
 */
export function zipRead(bytes, name, maxBytes) {
  const matches = zipEntries(bytes).filter((e) => e.name === name);
  if (matches.length !== 1) throw new RangeError(`zip: ${matches.length} entries named ${name}`);
  const e = matches[0];
  if (e.flags & 0x1) throw new RangeError(`zip: ${name} is encrypted`);
  if (e.method !== 0 && e.method !== 8) throw new RangeError(`zip: ${name} uses compression method ${e.method}`);
  if (e.size > maxBytes) throw new RangeError(`zip: ${name} is ${e.size} bytes, over the limit ${maxBytes}`);
  const h = e.offset;
  if (h + 30 > bytes.length || bytes.readUInt32LE(h) !== LOCAL) throw new RangeError(`zip: ${name} has no local header`);
  const dataStart = h + 30 + bytes.readUInt16LE(h + 26) + bytes.readUInt16LE(h + 28);
  if (dataStart + e.compressedSize > bytes.length) throw new RangeError(`zip: ${name} runs past the end of the file`);
  const data = bytes.subarray(dataStart, dataStart + e.compressedSize);
  const out = e.method === 0 ? Buffer.from(data) : inflateRawSync(data, { maxOutputLength: maxBytes });
  if (out.length !== e.size) throw new RangeError(`zip: ${name} inflates to ${out.length} bytes, stated ${e.size}`);
  if (crc32(out) !== e.crc) throw new RangeError(`zip: ${name} fails its CRC-32`);
  return out;
}

/**
 * Writes a zip of [{ name, data }] with deflate and a fixed date, so the same input always
 * gives the same bytes. Used for fixtures only.
 */
export function zipWrite(files) {
  const locals = [];
  const centrals = [];
  let offset = 0;
  const DATE = 0x5b6d; // 2025-11-13, a fixed stamp
  for (const f of files) {
    const name = Buffer.from(f.name, 'utf8');
    const data = Buffer.isBuffer(f.data) ? f.data : Buffer.from(f.data, 'utf8');
    const packed = deflateRawSync(data, { level: 9 });
    const crc = crc32(data);
    const local = Buffer.alloc(30);
    local.writeUInt32LE(LOCAL, 0);
    local.writeUInt16LE(20, 4);
    local.writeUInt16LE(0x0800, 6);
    local.writeUInt16LE(8, 8);
    local.writeUInt16LE(0, 10);
    local.writeUInt16LE(DATE, 12);
    local.writeUInt32LE(crc, 14);
    local.writeUInt32LE(packed.length, 18);
    local.writeUInt32LE(data.length, 22);
    local.writeUInt16LE(name.length, 26);
    locals.push(local, name, packed);
    const central = Buffer.alloc(46);
    central.writeUInt32LE(CENTRAL, 0);
    central.writeUInt16LE(20, 4);
    central.writeUInt16LE(20, 6);
    central.writeUInt16LE(0x0800, 8);
    central.writeUInt16LE(8, 10);
    central.writeUInt16LE(0, 12);
    central.writeUInt16LE(DATE, 14);
    central.writeUInt32LE(crc, 16);
    central.writeUInt32LE(packed.length, 20);
    central.writeUInt32LE(data.length, 24);
    central.writeUInt16LE(name.length, 28);
    central.writeUInt32LE(offset, 42);
    centrals.push(central, name);
    offset += 30 + name.length + packed.length;
  }
  const dir = Buffer.concat(centrals);
  const end = Buffer.alloc(22);
  end.writeUInt32LE(EOCD, 0);
  end.writeUInt16LE(files.length, 8);
  end.writeUInt16LE(files.length, 10);
  end.writeUInt32LE(dir.length, 12);
  end.writeUInt32LE(offset, 16);
  return Buffer.concat([...locals, dir, end]);
}
