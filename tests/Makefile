CFLAGS = -std=c99 -Wall -Wextra -Wno-unused-result -O1 -g -fsanitize=address,undefined

test: nano_install_test
	./nano_install_test

nano_install_test: nano_install_test.c ../platforms/nano/rh_install.c ../core/sha256.c
	$(CC) $(CFLAGS) -o $@ nano_install_test.c ../platforms/nano/rh_install.c ../core/sha256.c

clean:
	rm -f nano_install_test ui_nav_test ui_ops_test

# Phase 4B UI test. SDL 1.2 + SDL_image prefix (static); WSL host: SDLP=$$HOME/sdlhost/inst
SDLP ?= $(HOME)/sdlhost/inst
UI_SRC = ../ui/rh_ui.c ../ui/rh_gfx.c ../ui/rh_model.c ../ui/rh_json.c
UI_LIBS = -L$(SDLP)/lib -lSDL_image -lSDL -lpng16 -lz -lm -lpthread -ldl

ui_nav_test: ui_nav_test.c $(UI_SRC) ../platforms/nano/rh_install.c ../ui/*.h
	$(CC) -std=gnu99 -Wall -Wextra -Wno-format-truncation -O1 -g -fsanitize=address,undefined -I$(SDLP)/include -o $@ ui_nav_test.c $(UI_SRC) ../platforms/nano/rh_install.c ../core/sha256.c $(UI_LIBS)

ui-test: ui_nav_test
	./ui_nav_test .. $(SHOTS)

# Phase 5C-1: UI + rh_ops + the real install engine (temp dirs only)
MBED ?= $(HOME)/mbedtls_native
OPS_SRC = $(UI_SRC) ../ui/rh_ops.c ../ui/rh_source.c ../platforms/nano/rh_install.c ../core/sha256.c ../core/rh_net.c ../core/rh_catalog.c ../core/rh_catalog_state.c mc_host.o mce_host.o
ui_ops_test: ui_ops_test.c $(OPS_SRC) ../ui/*.h
	$(CC) -std=gnu99 -Wall -Wextra -Wno-format-truncation -O1 -g -fsanitize=address,undefined -I$(SDLP)/include -I$(MBED)/include -o $@ ui_ops_test.c $(OPS_SRC) $(UI_LIBS) -L$(MBED)/library -lmbedtls -lmbedx509 -lmbedcrypto

ops-test: ui_ops_test
	./ui_ops_test .. $(SHOTS)

# Phase 6C-2: native signed-catalog verifier (Monocypher vendored under ../vendor/monocypher)
MC = ../vendor/monocypher
CAT_C = ../core/rh_catalog.c ../core/rh_catalog_state.c ../core/sha256.c
CAT_FLAGS = -std=c99 -Wall -Wextra -Wno-unused-result
mc_host.o: $(MC)/monocypher.c $(MC)/monocypher.h
	$(CC) -std=c99 -O2 -c -o $@ $(MC)/monocypher.c
mce_host.o: $(MC)/monocypher-ed25519.c $(MC)/monocypher-ed25519.h
	$(CC) -std=c99 -O2 -c -o $@ $(MC)/monocypher-ed25519.c
trust_native_test: trust_native_test.c rfc8032_vectors.h $(CAT_C) ../core/rh_catalog.h mc_host.o mce_host.o
	$(CC) $(CAT_FLAGS) -O1 -g -fsanitize=address,undefined -o $@ trust_native_test.c $(CAT_C) mc_host.o mce_host.o
native-test: trust_native_test
	./trust_native_test
# sanitizer build for differential/fuzz runs, plain -O2 build for performance numbers
../build/rh_verify_asan: ../platforms/nano/cli/rh_verify_cli.c $(CAT_C) mc_host.o mce_host.o
	mkdir -p ../build && $(CC) $(CAT_FLAGS) -O1 -g -fsanitize=address,undefined -o $@ ../platforms/nano/cli/rh_verify_cli.c $(CAT_C) mc_host.o mce_host.o
../build/rh_verify_host: ../platforms/nano/cli/rh_verify_cli.c $(CAT_C) mc_host.o mce_host.o
	mkdir -p ../build && $(CC) $(CAT_FLAGS) -O2 -o $@ ../platforms/nano/cli/rh_verify_cli.c $(CAT_C) mc_host.o mce_host.o
native-tools: ../build/rh_verify_asan ../build/rh_verify_host
trust_state_test: trust_state_test.c $(CAT_C) ../core/rh_catalog_state.h mc_host.o mce_host.o
	$(CC) $(CAT_FLAGS) -O1 -g -fsanitize=address,undefined -o $@ trust_state_test.c $(CAT_C) mc_host.o mce_host.o
state-test: trust_state_test
	./trust_state_test

# Phase 7: HTTPS client (mbedTLS 2.16.9: host build in $(MBED), ARM build from the Buildroot sysroot)
MBED ?= $(HOME)/mbedtls_native
../build/rh_get_asan: ../platforms/nano/cli/rh_net_cli.c ../core/rh_net.c ../core/rh_net.h ../core/sha256.c
	mkdir -p ../build && $(CC) -std=c99 -Wall -Wextra -Wno-unused-result -O1 -g -fsanitize=address,undefined -I$(MBED)/include -o $@ \
		../platforms/nano/cli/rh_net_cli.c ../core/rh_net.c ../core/sha256.c -L$(MBED)/library -lmbedtls -lmbedx509 -lmbedcrypto

# Phase 7: DEV flow with a signed catalog over real TLS (driven by test_signed_flow.py)
ui_signed_test: ui_signed_test.c $(OPS_SRC) ../ui/*.h
	$(CC) -std=gnu99 -Wall -Wextra -Wno-format-truncation -O1 -g -fsanitize=address,undefined -I$(SDLP)/include -I$(MBED)/include -o $@ ui_signed_test.c $(OPS_SRC) $(UI_LIBS) -L$(MBED)/library -lmbedtls -lmbedx509 -lmbedcrypto
