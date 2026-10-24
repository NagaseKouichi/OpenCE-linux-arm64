"""Execute the production LP64 startup and XDVDFS importer, without game data."""
import os
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
HOST = ROOT / 'port/linux_arm64/host'

HARNESS = r'''
#include "host_startup.h"
#include "xiso.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static int ask(void *p, const char *d) { (void)d; return atoi(p); }
static int choose(void *p, char *b, size_t n) { (void)p; (void)b; (void)n; return 0; }
static int extract(void *p, const char *i, const char *d, char *e, size_t n) {
 (void)p; return xiso_extract_maps(i,d,NULL,NULL,e,(int)n);
}
int main(int argc, char **argv) {
 struct host_startup paths; char error[1024] = "";
 if (!host_startup_resolve(&paths,argv[1],error,sizeof(error))) { puts(error); return 2; }
 if (argc > 2) {
  struct host_import_ui ui = { ask, choose, extract, argc > 3 ? argv[3] : "0" };
  int r = host_startup_import(&paths,strcmp(argv[2],"prompt") ? argv[2] : NULL,&ui,error,sizeof(error));
  printf("result=%d\n%s\n",r,error); if(r < 0) return 3;
 }
 printf("data=%s\nsaves=%s\nconfig=%s\n",paths.data,paths.saves,paths.config);
 return 0;
}
'''

def image(path, name=b'ui.map', truncated=False, partition=0):
    data = bytearray(38 * 2048)
    magic = b'MICROSOFT*XBOX*MEDIA'
    data[0x10000:0x10000+20] = magic
    data[0x10000+20:0x10000+28] = struct.pack('<II',33,2048)
    data[0x107ec:0x10800] = magic
    def entry(sector, child, size, attr, name):
        start=sector*2048
        data[start:start+14] = struct.pack('<HHIIBB',0,0,child,size,attr,len(name))
        data[start+14:start+14+len(name)] = name
    entry(33,34,2048,16,b'maps')
    entry(34,37,5000 if truncated else 7,0,name)
    data[37*2048:37*2048+7] = b'fixture'
    with path.open('wb') as f:
        f.seek(partition)
        f.write(data)

class StartupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.build = tempfile.TemporaryDirectory()
        p=Path(cls.build.name)
        (p/'main.c').write_text(HARNESS)
        cls.binary=p/'startup'
        cls.compile=subprocess.run(['cc','-D_GNU_SOURCE','-D_FILE_OFFSET_BITS=64',
            '-DHALO_LINUX_ARM64_HOST=1','-DHALO_HOST_POSIX_FILES=1',f'-I{HOST}',f'-I{ROOT}/port/linux/src',
            f'-I{ROOT}/port/third_party/tomlc17',str(p/'main.c'),str(HOST/'host_startup.c'),
            str(HOST/'host_xiso.c'),str(ROOT/'port/linux/src/xiso.c'),
            str(ROOT/'port/linux/src/posix_files.c'),
            str(ROOT/'port/third_party/tomlc17/tomlc17.c'),'-o',str(cls.binary)],
            capture_output=True,text=True)
    @classmethod
    def tearDownClass(cls): cls.build.cleanup()
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name); self.cwd=self.root/'cwd'; self.cwd.mkdir()
        self.exe=self.root/'build/linux_arm64'; self.exe.mkdir(parents=True)
        self.env={k:v for k,v in os.environ.items() if not k.startswith('HALO_')}
        self.env.update(HOME=str(self.root/'home'),XDG_DATA_HOME=str(self.root/'xdg'))
    def run_start(self,*args):
        self.assertEqual(self.compile.returncode,0,'Production startup API missing: '+self.compile.stderr)
        r=subprocess.run([str(self.binary),str(self.exe/'halo-host'),*map(str,args)],
            cwd=self.cwd,env=self.env,capture_output=True,text=True,timeout=30)
        return r,dict(line.split('=',1) for line in r.stdout.splitlines() if '=' in line)
    def maps(self,p): (p/'MaPs').mkdir()
    def test_cwd_maps_and_default_saves(self):
        self.maps(self.cwd); r,p=self.run_start()
        self.assertEqual(r.returncode,0,r.stdout); self.assertEqual(p['data'],str(self.cwd))
        self.assertEqual(p['saves'],str(self.root/'xdg/halo-linux'))
    def test_exe_before_cwd_assets(self):
        self.maps(self.exe); (self.cwd/'assets/maps').mkdir(parents=True)
        _,p=self.run_start(); self.assertEqual(p['data'],str(self.exe))
    def test_assets_fallbacks(self):
        (self.cwd/'assets/maps').mkdir(parents=True)
        _,p=self.run_start(); self.assertEqual(p['data'],str(self.cwd/'assets'))
        (self.cwd/'assets/maps').rmdir(); (self.root/'assets/maps').mkdir(parents=True)
        _,p=self.run_start(); self.assertEqual(p['data'],str(self.root/'assets'))
    def test_config_and_env_precedence(self):
        (self.exe/'config.toml').write_text("[paths]\ndata='exe-data'\nsaves='exe-saves'\n")
        _,p=self.run_start(); self.assertEqual(p['data'],str(self.cwd/'exe-data'))
        (self.exe/'config.toml').write_text("[paths]\ndata='data'\nsaves='saves'\n[display]\nmode='windowed'\n")
        (self.cwd/'config.toml').write_text("[paths]\ndata='unrelated'\n")
        _,p=self.run_start(); self.assertEqual(p['config'],str(self.exe/'config.toml'))
        self.assertEqual(p['data'],str(self.cwd/'data')); self.assertEqual(p['saves'],str(self.cwd/'saves'))
        self.env.update(HALO_DATA_ROOT='override',HALO_SAVE_ROOT='override-save')
        _,p=self.run_start(); self.assertEqual(p['data'],str(self.cwd/'override'))
        self.assertEqual(p['saves'],str(self.cwd/'override-save'))
    def test_executable_config_not_shadowed_by_working_directory(self):
        (self.exe/'config.toml').write_text("[paths]\ndata='exe-data'\nsaves='exe-save'\n")
        (self.cwd/'config.toml').write_text("[paths]\ndata='unrelated-data'\n")
        result, paths = self.run_start()
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual(paths['config'], str(self.exe/'config.toml'))
        self.assertEqual(paths['data'], str(self.cwd/'exe-data'))
        self.assertEqual(paths['saves'], str(self.cwd/'exe-save'))

    def test_missing_maps_destination_is_exe_not_arbitrary_data(self):
        (self.cwd/'data/maps').mkdir(parents=True)
        _,p=self.run_start(); self.assertEqual(p['data'],str(self.exe))
    def test_no_and_picker_cancel_are_clean(self):
        for answer in ('0','1'):
            r,p=self.run_start('prompt',answer)
            self.assertEqual(r.returncode,0,r.stdout); self.assertEqual(p['result'],'0')
            self.assertFalse((self.exe/'maps').exists())
    def test_production_import_is_atomic(self):
        iso=self.root/'synthetic.iso'; image(iso)
        r,p=self.run_start(iso); self.assertEqual(r.returncode,0,r.stdout)
        self.assertEqual(p['result'],'1'); self.assertEqual((self.exe/'maps/ui.map').read_bytes(),b'fixture')
        self.assertFalse((self.exe/'maps.partial').exists())
    def test_partial_image_never_publishes_maps(self):
        iso=self.root/'short.iso'; image(iso,truncated=True)
        r,p=self.run_start(iso); self.assertEqual(r.returncode,3,r.stdout)
        self.assertFalse((self.exe/'maps').exists())
    def test_selected_config_reaches_real_guest_config_parser(self):
        prefix=self.root/'prefix.h'
        prefix.write_text('#define __HALO_LINUX_PLATFORM_H\nvoid platform_log(const char *, ...);\n')
        source=self.root/'config.c'
        source.write_text('#include "port_config.h"\n#include <stdio.h>\nvoid platform_log(const char *s, ...) {(void)s;}\nint main(void) {printf("%s %g\\n", config_string("display.mode"),config_real("debug.exit_after"));}\n')
        binary=self.root/'config-test'
        c=subprocess.run(['cc','-D_GNU_SOURCE','-DHALO_ANDROID','-DHALO_ARM64_GUEST',
            '-DHALO_LINUX_ARM64','-include',str(prefix),f'-I{ROOT}/port/linux/src',
            f'-I{ROOT}/port/third_party/tomlc17',f'-I{ROOT}/build/linux_arm64/third_party/SDL3/include',
            str(source),str(ROOT/'port/linux/src/port_config.c'),
            str(ROOT/'port/third_party/tomlc17/tomlc17.c'),'-pthread','-o',str(binary)],capture_output=True,text=True)
        self.assertEqual(c.returncode,0,c.stderr)
        config=self.cwd/'config.toml'; config.write_text("[display]\nmode='windowed'\n[debug]\nexit_after=2.5\n")
        env={**self.env,'HALO_DATA_ROOT':str(self.root/'other'),'HALO_CONFIG_PATH':str(config)}
        r=subprocess.run([str(binary)],env=env,capture_output=True,text=True)
        self.assertEqual(r.stdout.strip(),'windowed 2.5')

    def test_cli_import_without_video(self):
        qemu=ROOT/'build/startup-qemu/root/usr/bin/qemu-aarch64-static'
        sysroot=ROOT/'build/startup-qemu/runtime-rootfs'
        host=ROOT/'build/linux_arm64/halo-host'
        if not qemu.exists() or not sysroot.exists() or not host.exists():
            self.skipTest('optional ARM64 runtime sysroot is not provisioned')
        iso=self.root/'headless.iso'; image(iso)
        env={**self.env, 'HALO_DATA_ROOT':str(self.root/'headless-data'),
             'SDL_VIDEODRIVER':'missing-driver',
             'LD_LIBRARY_PATH':str(ROOT/'build/linux_arm64/sdl3-build')}
        r=subprocess.run([str(qemu),'-L',str(sysroot),str(host),'--import-iso',str(iso),'--print-paths'],
                         env=env,cwd=self.cwd,capture_output=True,text=True,timeout=30)
        self.assertEqual(r.returncode,0,r.stderr)
        self.assertEqual((self.root/'headless-data/maps/ui.map').read_bytes(),b'fixture')

    def test_retry_removes_stale_partial_files(self):
        partial = self.exe/'maps.partial'
        partial.mkdir()
        (partial/'stale.map').write_bytes(b'interrupted')
        iso = self.root/'retry.iso'; image(iso)
        result, _ = self.run_start(iso)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual((self.exe/'maps/ui.map').read_bytes(), b'fixture')
        self.assertFalse((self.exe/'maps/stale.map').exists())

    def test_duplicate_casefolded_names_cannot_overwrite_first_file(self):
        iso = self.root/'duplicates.iso'; image(iso)
        with iso.open('r+b') as stream:
            stream.seek(34*2048+2); stream.write(struct.pack('<H', 8))
            stream.seek(34*2048+32)
            stream.write(struct.pack('<HHIIBB', 0, 0, 36, 7, 0, 6)+b'UI.MAP')
            stream.seek(36*2048); stream.write(b'changed')
        result, _ = self.run_start(iso)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual((self.exe/'maps/ui.map').read_bytes(), b'fixture')
        self.assertFalse((self.exe/'maps/UI.MAP').exists())

    def test_directory_cycle_terminates_after_visiting_each_entry_once(self):
        iso = self.root/'cycle.iso'; image(iso)
        with iso.open('r+b') as stream:
            stream.seek(34*2048+2); stream.write(struct.pack('<H', 8))
            stream.seek(34*2048+32)
            stream.write(struct.pack('<HHIIBB', 0, 8, 37, 7, 0, 9)+b'other.map')
        result, _ = self.run_start(iso)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual(sorted(p.name for p in (self.exe/'maps').iterdir()),
                         ['other.map', 'ui.map'])

    def test_whole_disc_offset_and_path_traversal(self):
        iso=self.root/'whole.iso'; image(iso,partition=0x18300000)
        r,_=self.run_start(iso); self.assertEqual(r.returncode,0,r.stdout)
        other=self.root/'bad.iso'; image(other,name=b'../ui.map')
        self.env['HALO_DATA_ROOT']=str(self.root/'bad'); (self.root/'bad').mkdir()
        r,_=self.run_start(other); self.assertEqual(r.returncode,3,r.stdout)
        self.assertFalse((self.root/'ui.map').exists())

if __name__=='__main__': unittest.main()
