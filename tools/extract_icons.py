import sys
import os
import io
import re
import argparse
import configparser

from PIL import Image
from war3structs.storage import CascStore
from war3structs.storage.casclib import CascError
from war3structs.plaintext import TxtParser

SD_MOD = 'war3.w3mod:'
HD_MOD = 'war3.w3mod:_hd.w3mod:'
DE_MOD = 'war3.w3mod:_de.w3mod:'

MOD_NAMES = {SD_MOD: 'sd', HD_MOD: 'hd', DE_MOD: 'de'}

INCLUDED = [
  'abilityskin.txt', 'unitskin.txt', 'itemfunc.txt',
  'humanupgradefunc.txt', 'neutralupgradefunc.txt', 'nightelfupgradefunc.txt',
  'orcupgradefunc.txt', 'undeadupgradefunc.txt'
]

# Unused in melee
SKIPPED = ['Aoth', 'Nmsr', 'Hddt']

ART_KEYS = ['Art', 'Art:sd', 'Art:hd', 'Art:de']

SECTION_RE = re.compile(r'^\[.+\]')

def dds2jpg(data, resize=False):
  jpg = Image.open(io.BytesIO(data))

  if resize:
    jpg = jpg.resize((resize, resize), Image.Resampling.BICUBIC)

  jpg = jpg.convert('YCbCr')
  out_jpg = io.BytesIO()
  jpg.save(out_jpg, format='JPEG')

  return out_jpg.getvalue()

def sanitize(contents):
  """Drop lines that can't be parsed (the game files have a few data bugs,
  e.g. a key without '='). Returns the cleaned text and the dropped lines."""

  kept = []
  dropped = []

  for line in contents.splitlines():
    stripped = line.strip()

    if (not stripped
        or stripped.startswith(('//', ';', '_'))
        or SECTION_RE.match(stripped)
        or '=' in stripped):
      kept.append(line)
    else:
      dropped.append(line)

  return '\n'.join(kept) + '\n', dropped

def parse_txt(contents):
  """Parse a game txt file. Returns the config and the lines that were
  dropped to make it parse."""

  contents, dropped = sanitize(contents)

  # Whatever the generic rule did not catch, drop the offending lines the
  # parser points out and try again.
  for _ in range(20):
    try:
      return TxtParser.parse(contents), dropped
    except configparser.MissingSectionHeaderError as err:
      bad = [err.lineno]
    except configparser.ParsingError as err:
      bad = [lineno for lineno, _ in err.errors]

    lines = contents.split('\n')
    dropped.extend(lines[n - 1] for n in bad if 0 < n <= len(lines))
    contents = '\n'.join(line for n, line in enumerate(lines, 1) if n not in bad)

  return TxtParser.parse(contents), dropped

def clean_art(value):
  """Normalize an Art value: first element of a comma list, .dds, lowercase."""

  if value is None:
    return None

  value = value.split(',')[0].strip().strip('"')
  if not value:
    return None

  value = value.lower()
  if value.endswith('.blp'):
    value = value[:-4] + '.dds'
  elif not os.path.splitext(value)[1]:
    value += '.dds'

  return value

class Reader():
  """Cached CASC reads. A missing file is cached as None."""

  def __init__(self, store):
    self.store = store
    self.cache = {}
    self.errors = []

  def read(self, path):
    if path not in self.cache:
      try:
        self.cache[path] = self.store.read(path)
      except CascError:
        self.cache[path] = None
      except Exception as err:
        self.errors.append((path, repr(err)))
        self.cache[path] = None

    return self.cache[path]

def collect_sections(reader, verbose):
  """Read all included txt files and return {id: {key: value}} for every
  section that has art, plus a list of errors."""

  sections = {}
  errors = []

  for txt in INCLUDED:
    path = 'war3.w3mod:units\\%s' % txt
    data = reader.read(path)
    if data is None:
      errors.append('%s: could not be read from the game files' % path)
      continue

    try:
      config, dropped = parse_txt(data.decode('utf-8'))
    except Exception as err:
      errors.append('%s: could not be parsed (%r), skipped' % (path, err))
      continue

    if dropped and verbose:
      for line in dropped:
        print('  %s: ignored malformed line: %s' % (txt, line.strip()))

    for name in config.sections():
      if name in SKIPPED:
        continue

      try:
        section = dict(config[name])
      except Exception as err:
        errors.append('%s [%s]: unreadable section (%r)' % (txt, name, err))
        continue

      # The last file that defines art for an id wins
      if any(key in section for key in ART_KEYS):
        sections[name] = section

  return sections, errors

def resolve(sections):
  """Work out, for each id, the candidate (mod, path) pairs of each set in
  order of preference."""

  candidates = {'sd': {}, 'hd': {}, 'de': {}}

  for id_, section in sections.items():
    source = None
    skinnable = (section.get('skinnableID') or '').strip()
    if skinnable and skinnable != id_:
      source = sections.get(skinnable)

    def art(*keys):
      for sec in (section, source):
        if sec is None:
          continue
        for key in keys:
          value = clean_art(sec.get(key))
          if value:
            return value

      return None

    sd = art('Art', 'Art:sd')
    hd = art('Art:hd')
    de = art('Art:de')

    def add(set_, mod, path):
      if path and (mod, path) not in candidates[set_].setdefault(id_, []):
        candidates[set_][id_].append((mod, path))

    add('sd', SD_MOD, sd)

    # An HD icon with the same name as the sd one is a common case, so an
    # id without Art:hd still looks into the hd archive.
    add('hd', HD_MOD, hd or sd)
    add('hd', DE_MOD, de or sd)
    add('hd', SD_MOD, sd)

    add('de', DE_MOD, de or sd)
    add('de', SD_MOD, de or sd)
    add('de', SD_MOD, sd)

  return candidates

def extract_set(reader, name, candidates, out_dir, resize, verbose):
  os.makedirs(out_dir, exist_ok=True)

  written = 0
  fell_back = 0
  missing = []
  failed = []

  for id_, options in candidates.items():
    done = False

    for index, (mod, path) in enumerate(options):
      data = reader.read(mod + path)
      if data is None:
        continue

      try:
        jpg = dds2jpg(data, resize=resize)
      except Exception as err:
        failed.append((id_, mod + path, repr(err)))
        continue

      try:
        with open(os.path.join(out_dir, id_ + '.jpg'), 'wb') as fh:
          fh.write(jpg)
      except OSError as err:
        failed.append((id_, mod + path, repr(err)))
        break

      written += 1
      done = True

      if index > 0:
        fell_back += 1
        if verbose:
          print('  %s fallback: %s resolved from %s (%s)' % (name.upper(), id_, MOD_NAMES[mod], path))

      break

    if not done and not any(f[0] == id_ for f in failed):
      missing.append((id_, [mod + path for mod, path in options]))

  return written, fell_back, missing, failed

def extract_icons(installation_dir, out_dir, sets=('sd', 'hd', 'de'), verbose=False):
  wc3 = CascStore(installation_dir)
  reader = Reader(wc3)

  print('Collecting icons...')
  sections, errors = collect_sections(reader, verbose)
  candidates = resolve(sections)

  layout = {
    'sd': (out_dir, False),
    'hd': (os.path.join(out_dir, 'hd'), 128),
    'de': (os.path.join(out_dir, 'de'), 128)
  }

  summary = []
  for name in ('sd', 'hd', 'de'):
    if name not in sets:
      continue

    print('Extracting %s icons...' % name.upper())
    path, resize = layout[name]
    written, fell_back, missing, failed = extract_set(
      reader, name, candidates[name], path, resize, verbose
    )
    summary.append((name, written, fell_back, missing, failed))

  print('')
  print('Summary:')
  for name, written, fell_back, missing, failed in summary:
    print('  %s: %d written (%d from a fallback source), %d missing, %d failed'
          % (name.upper(), written, fell_back, len(missing), len(failed)))

  if verbose:
    for name, written, fell_back, missing, failed in summary:
      for id_, paths in missing:
        print('  %s missing: %s (%s)' % (name.upper(), id_, ', '.join(paths)))
      for id_, path, err in failed:
        print('  %s failed: %s (%s): %s' % (name.upper(), id_, path, err))

  for error in errors:
    print('  error: %s' % error)
  if verbose:
    for path, err in reader.errors:
      print('  error: reading %s: %s' % (path, err))
  elif reader.errors:
    print('  %d unexpected read errors (use -v to list)' % len(reader.errors))

def main():
  parser = argparse.ArgumentParser(description='Extract command button icons from a Warcraft III installation.')
  parser.add_argument('installation_dir', help='Warcraft III installation directory')
  parser.add_argument('out_dir', help='directory to write the icons to (hd/ and de/ subdirectories are created)')
  parser.add_argument('--sets', default='sd,hd,de', help='comma separated icon sets to extract (default: sd,hd,de)')
  parser.add_argument('-v', '--verbose', action='store_true', help='list ignored lines, fallbacks and missing icons')
  args = parser.parse_args()

  sets = [s.strip().lower() for s in args.sets.split(',') if s.strip()]
  unknown = [s for s in sets if s not in ('sd', 'hd', 'de')]
  if unknown or not sets:
    parser.error('unknown icon set(s): %s' % ', '.join(unknown or ['(none)']))

  try:
    extract_icons(args.installation_dir, args.out_dir, sets, args.verbose)
  except Exception as err:
    print('Fatal error: %s' % err, file=sys.stderr)
    sys.exit(1)

if __name__ == '__main__':
  main()
