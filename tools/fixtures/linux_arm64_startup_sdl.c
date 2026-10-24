/* Asset-free probe: real production SDL importer, then guest-style SDL_Init. */
#include "host_startup.h"
#include <SDL3/SDL.h>
#include <SDL3/SDL_main.h>
#include <stdio.h>
#include <string.h>
int main(int argc, char **argv) {
    struct host_startup paths;
    char error[1024]="";
    SDL_SetMainReady();
    if (!SDL_Init(0) || !SDL_IsMainThread()) return 10;
    if (!host_startup_resolve(&paths,argv[0],error,sizeof(error))) return 11;
    if (argc>2 && !strcmp(argv[2],"cancel")) {
        if (!SDL_Init(SDL_INIT_VIDEO)) return 12;
        SDL_Event event={0}; event.type=SDL_EVENT_QUIT; SDL_PushEvent(&event);
    }
    int result=host_startup_sdl_import(&paths,argv[1],error,sizeof(error));
    if (result!=1) { fprintf(stderr,"%s\n",error); return 13; }
    if (SDL_WasInit(SDL_INIT_VIDEO)) return 14;
    if (!SDL_Init(SDL_INIT_VIDEO) || !SDL_IsMainThread()) return 15;
    SDL_Window *window=SDL_CreateWindow("guest-style reinit",64,64,SDL_WINDOW_HIDDEN);
    if (!window) return 16;
    SDL_DestroyWindow(window); SDL_Quit();
    puts("import/reinit OK: SDL video released, same main thread, new guest window");
    return 0;
}
