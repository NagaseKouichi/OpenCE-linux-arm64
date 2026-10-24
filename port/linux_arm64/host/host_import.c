/* SDL importer runs on the same low-stack SDL main thread as the guest. */
#include "host_startup.h"
#include "xiso.h"
#include <SDL3/SDL.h>
#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
struct data_extraction
{
	pthread_mutex_t lock;
	char image[1024];
	char destination[1024];
	char file[256];
	unsigned long long done;
	unsigned long long total;
	int finished;
	int succeeded;
	char error[512];
};

static void data_extraction_progress(void *context, const char *file, unsigned long long done,
	unsigned long long total)
{
	struct data_extraction *extraction = context;

	pthread_mutex_lock(&extraction->lock);
	snprintf(extraction->file, sizeof(extraction->file), "%s", file);
	extraction->done = done;
	extraction->total = total;
	pthread_mutex_unlock(&extraction->lock);
}

static void *data_extraction_thread(void *context)
{
	struct data_extraction *extraction = context;
	int succeeded = xiso_extract_maps(extraction->image, extraction->destination, data_extraction_progress,
		extraction, extraction->error, sizeof(extraction->error)) != 0;

	pthread_mutex_lock(&extraction->lock);
	extraction->succeeded = succeeded;
	extraction->finished = 1;
	pthread_mutex_unlock(&extraction->lock);
	return NULL;
}

/* copies the maps, showing how far it has got; closing the window quits */
static int data_extract(const char *image, const char *destination, char *error, int error_size)
{
	static struct data_extraction extraction;
	SDL_Window *window;
	SDL_Renderer *renderer = NULL;
	pthread_t thread;
	int finished = 0;

	memset(&extraction, 0, sizeof(extraction));
	pthread_mutex_init(&extraction.lock, NULL);
	snprintf(extraction.image, sizeof(extraction.image), "%s", image);
	snprintf(extraction.destination, sizeof(extraction.destination), "%s", destination);
	if (pthread_create(&thread, NULL, data_extraction_thread, &extraction) != 0)
	{
		snprintf(error, (size_t)error_size, "Could not start the extraction.");
		return 0;
	}
	/* (waited for through extraction.finished; the Windows port's threads
	cannot be joined) */
	/* Joined after the progress loop, before SDL shutdown. */
	window = SDL_CreateWindow("Halo", 640, 150, 0);
	if (window)
	{
		renderer = SDL_CreateRenderer(window, NULL);
		if (renderer)
			SDL_SetRenderVSync(renderer, 1);
	}
	while (!finished)
	{
		SDL_Event event;
		char file[256];
		unsigned long long done, total;

		while (SDL_PollEvent(&event))
		{
			if (event.type == SDL_EVENT_QUIT || event.type == SDL_EVENT_WINDOW_CLOSE_REQUESTED)
			{
				platform_log("extraction cancelled");
				SDL_Quit();
				exit(EXIT_SUCCESS);
			}
		}
		pthread_mutex_lock(&extraction.lock);
		finished = extraction.finished;
		snprintf(file, sizeof(file), "%s", extraction.file);
		done = extraction.done;
		total = extraction.total;
		pthread_mutex_unlock(&extraction.lock);
		if (renderer)
		{
			char line[320];
			SDL_FRect bar = { 20.0f, 100.0f, 600.0f, 24.0f };
			float fraction = total ? (float)((double)done / (double)total) : 0.0f;

			SDL_SetRenderDrawColor(renderer, 12, 16, 20, 255);
			SDL_RenderClear(renderer);
			SDL_SetRenderDrawColor(renderer, 230, 230, 230, 255);
			SDL_SetRenderScale(renderer, 2.0f, 2.0f);
			SDL_RenderDebugText(renderer, 10.0f, 10.0f, "Extracting the maps folder...");
			SDL_SetRenderScale(renderer, 1.0f, 1.0f);
			snprintf(line, sizeof(line), "%s  (%llu of %llu MB)", file, done >> 20, total >> 20);
			SDL_RenderDebugText(renderer, 20.0f, 70.0f, line);
			SDL_SetRenderDrawColor(renderer, 60, 66, 72, 255);
			SDL_RenderFillRect(renderer, &bar);
			bar.w *= fraction;
			SDL_SetRenderDrawColor(renderer, 90, 160, 90, 255);
			SDL_RenderFillRect(renderer, &bar);
			SDL_RenderPresent(renderer);
		}
		SDL_Delay(16);
	}
	pthread_join(thread, NULL);
	pthread_mutex_destroy(&extraction.lock);
	if (renderer)
		SDL_DestroyRenderer(renderer);
	if (window)
		SDL_DestroyWindow(window);
	if (!extraction.succeeded)
		snprintf(error, (size_t)error_size, "%s", extraction.error);
	return extraction.succeeded;
}

struct data_image_choice
{
	SDL_AtomicInt done;
	char path[PATH_MAX];
};

static void SDLCALL data_image_chosen(void *userdata, const char * const *files, int filter)
{
	struct data_image_choice *choice = userdata;

	(void)filter;
	if (!files) snprintf(choice->path, sizeof(choice->path), "!dialog-error");
	else if (files[0])
		snprintf(choice->path, sizeof(choice->path), "%s", files[0]);
	SDL_SetAtomicInt(&choice->done, 1);
}

/* the disc image the player picks; 0 if they pick none */
static int data_choose_image(char *path, int size)
{
	static const SDL_DialogFileFilter filters[] =
	{
		{ "Xbox disc images", "iso;xiso" },
		{ "All files", "*" },
	};
	static struct data_image_choice choice;

	memset(&choice, 0, sizeof(choice));
	SDL_ShowOpenFileDialog(data_image_chosen, &choice, NULL, filters, 2, NULL, false);
	/* the dialog answers through events (and on some systems another
	thread) */
	while (!SDL_GetAtomicInt(&choice.done))
	{
		SDL_PumpEvents();
		SDL_Delay(50);
	}
	if (!strcmp(choice.path, "!dialog-error")) return -1;
	if (!choice.path[0])
		return 0;
	snprintf(path, (size_t)size, "%s", choice.path);
	return 1;
}


static int ask(void *context, const char *destination) {
    (void)context;
    static const SDL_MessageBoxButtonData buttons[] = {
        { SDL_MESSAGEBOX_BUTTON_RETURNKEY_DEFAULT, 1, "Yes" },
        { SDL_MESSAGEBOX_BUTTON_ESCAPEKEY_DEFAULT, 0, "No" }
    };
    char message[PATH_MAX+512]; int answer=0;
    snprintf(message,sizeof(message),
        "Halo's maps folder was not found.\n\nExtract maps from your Halo: Combat Evolved Xbox ISO/XISO?\n"
        "They will be copied to %s/maps.\n\nOr set paths.data in config.toml or HALO_DATA_ROOT to a writable data folder.",destination);
    SDL_MessageBoxData question={SDL_MESSAGEBOX_INFORMATION,NULL,"Halo",message,2,buttons,NULL};
    return SDL_ShowMessageBox(&question,&answer) ? answer : -1;
}
static int choose(void *context, char *path, size_t size) {
    (void)context; return data_choose_image(path,(int)size);
}
static int extract(void *context, const char *image, const char *destination, char *error, size_t size) {
    (void)context; return data_extract(image,destination,error,(int)size);
}
static int extract_direct(void *context, const char *image, const char *destination, char *error, size_t size) {
    (void)context;
    return xiso_extract_maps(image,destination,NULL,NULL,error,(int)size);
}
int host_startup_sdl_import(struct host_startup *paths, const char *iso, char *error, size_t size) {
    if (paths->maps_found && !iso) return 1;
    /* Explicit CLI import needs no display, portal or file picker. */
    if (iso) {
        struct host_import_ui direct={NULL,NULL,extract_direct,NULL};
        return host_startup_import(paths,iso,&direct,error,size);
    }
    if (!SDL_Init(SDL_INIT_VIDEO)) {
        snprintf(error,size,"Cannot initialize import display: %s. Set paths.data/HALO_DATA_ROOT to extracted maps.",SDL_GetError());
        return -1;
    }
    struct host_import_ui ui={ask,choose,extract,NULL};
    int result=host_startup_import(paths,iso,&ui,error,size);
    /* Release import windows/video before guest SDL_Init. Thread identity stays
       on this thread; no SDL calls occur on the original launcher thread. */
    SDL_Quit();
    return result;
}
