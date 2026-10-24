"""Original numeric regression cases; contains no disc-derived payload."""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class RetailTagCacheLayoutTests(unittest.TestCase):
    def test_retail_bsp_fits_without_overlapping_game_state(self):
        # Retail BSP ceiling observed in the user's Xbox map references.
        source = r'''
#include "source/cache/physical_memory_map.h"
#include "port/linux/include/halo_port_capacity.h"
#define TAG_BASE 0x803A6000u
_Static_assert(0x81A22800u + 0x800u <= TAG_BASE + TAG_CACHE_SIZE,
               "retail UI BSP lies outside the tag cache");
_Static_assert(TAG_BASE + TAG_CACHE_SIZE <= HALO_PORT_GAME_STATE_BASE_ADDRESS,
               "tag cache overlaps game state");
_Static_assert(HALO_PORT_GAME_STATE_BASE_ADDRESS + HALO_PORT_GAME_STATE_SIZE < 0x88000000u,
               "game state lies outside the ARM64 guest window");
int main(void) { return 0; }
'''
        with tempfile.TemporaryDirectory() as directory:
            src = Path(directory) / 'layout.c'
            src.write_text(source)
            result = subprocess.run(['cc', '-std=c11', '-I', str(ROOT), '-fsyntax-only', str(src)],
                                    text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    unittest.main()
