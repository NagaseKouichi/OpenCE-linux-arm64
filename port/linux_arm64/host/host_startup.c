/* Mirrors xbox_files.c search order and executable-local desktop config. */
#include "host_startup.h"
#include "tomlc17.h"
#include <dirent.h>
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

static int join(char *out, const char *a, const char *b) {
    return snprintf(out, PATH_MAX, "%s%s%s", a, *b ? "/" : "", b) < PATH_MAX;
}
static int absolute(char *out, const char *path, const char *cwd) {
    return *path == '/' ? join(out,path,"") : join(out,cwd,path);
}
static int has_maps(const char *path) {
    DIR *dir=opendir(path); struct dirent *entry; int found=0;
    if (!dir) return 0;
    while ((entry=readdir(dir))) if (!strcasecmp(entry->d_name,"maps")) { found=1; break; }
    closedir(dir); return found;
}
int host_startup_resolve(struct host_startup *p, const char *exe, char *error, size_t n) {
    char cwd[PATH_MAX], base[PATH_MAX], candidate[PATH_MAX];
    const char *data=getenv("HALO_DATA_ROOT"), *save=getenv("HALO_SAVE_ROOT");
    const char *xdg=getenv("XDG_DATA_HOME"), *home=getenv("HOME");
    memset(p,0,sizeof(*p));
    if (!getcwd(cwd,sizeof(cwd)) || !absolute(base,exe,cwd)) goto too_long;
    char *slash=strrchr(base,'/'); if (slash) *slash=0;
    if (!join(p->config,base,"config.toml")) goto too_long;
    toml_result_t config=toml_parse_file_ex(p->config);
    if (config.ok) {
        toml_datum_t d=toml_seek(config.toptab,"paths.data"), s=toml_seek(config.toptab,"paths.saves");
        if ((!data || !*data) && d.type==TOML_STRING) data=d.u.str.ptr;
        if ((!save || !*save) && s.type==TOML_STRING) save=s.u.str.ptr;
    }
    int ok=1;
    if (data && *data) ok=absolute(p->data,data,cwd);
    else if (has_maps(cwd)) ok=join(p->data,cwd,"");
    else if (has_maps(base)) ok=join(p->data,base,"");
    else {
        ok=join(candidate,cwd,"assets");
        if (ok && has_maps(candidate)) ok=join(p->data,candidate,"");
        else {
            char repo[PATH_MAX]; join(repo,base,"");
            for (int i=0;i<2;i++) { slash=strrchr(repo,'/'); if (slash) *slash=0; }
            ok=ok && join(candidate,repo,"assets");
            ok=ok && join(p->data,has_maps(candidate) ? candidate : base,"");
        }
    }
    if (save && *save) ok=ok && absolute(p->saves,save,cwd);
    else if (xdg && *xdg) ok=ok && absolute(candidate,xdg,cwd) && join(p->saves,candidate,"halo-linux");
    else if (home && *home) ok=ok && absolute(candidate,home,cwd) && join(p->saves,candidate,".local/share/halo-linux");
    else ok=ok && join(p->saves,p->data,"");
    if (config.ok) toml_free(config);
    else if (access(p->config,F_OK)==0) fprintf(stderr,"halo: config %s: %s; using defaults\n",p->config,config.errmsg);
    if (!ok) goto too_long;
    p->maps_found=has_maps(p->data); return 1;
 too_long:
    snprintf(error,n,"Startup path is too long or current directory is inaccessible."); return 0;
}
int host_startup_mkdir(const char *path, char *error, size_t n) {
    char copy[PATH_MAX]; if (!join(copy,path,"")) return 0;
    for (char *at=copy+1;;at++) {
        if (*at && *at!='/') continue;
        char saved=*at; *at=0;
        struct stat info;
        if ((mkdir(copy,0700) && errno!=EEXIST) || stat(copy,&info) || !S_ISDIR(info.st_mode)) {
            snprintf(error,n,"Cannot create %s: %s. Choose a writable folder with paths.data/paths.saves in config.toml or HALO_DATA_ROOT/HALO_SAVE_ROOT.",copy,strerror(errno)); return 0;
        }
        *at=saved; if (!saved) break;
    }
    return 1;
}
int host_startup_import(struct host_startup *p, const char *iso, const struct host_import_ui *ui, char *error, size_t n) {
    char image[PATH_MAX];
    if (p->maps_found && !iso) return 1;
    if (!iso) {
        int answer=ui->ask(ui->context,p->data);
        if (answer<0) { snprintf(error,n,"Cannot show import prompt; use --import-iso PATH or set paths.data/HALO_DATA_ROOT."); return -1; }
        if (!answer) return 0;
        int choice=ui->choose(ui->context,image,sizeof(image));
        if (choice<0) { snprintf(error,n,"Cannot open file picker; use --import-iso PATH."); return -1; }
        if (!choice) return 0;
        iso=image;
    }
    if (!host_startup_mkdir(p->data,error,n)) return -1;
    if (!ui->extract(ui->context,iso,p->data,error,n)) {
        size_t used=strlen(error);
        snprintf(error+used,n>used ? n-used : 0," Choose a writable paths.data or HALO_DATA_ROOT; --import-iso PATH is available."); return -1;
    }
    p->maps_found=has_maps(p->data); return p->maps_found ? 1 : -1;
}
