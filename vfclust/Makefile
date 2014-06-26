CC = gcc
AR = ar
LIB= -lm

CFLAGS += -O3
# CFLAGS += -g
# CFLAGS += -DALPHA
# CFLAGS += -DDEBUG

# Flags for GCC
CFLAGS += -Wall

# for 32 bit architechture
ARCH = -m32

# for 64 bit architechture
#ARCH = -m64



all: clean t2p1 test

t2p1:
	$(CC) $(CFLAGS) $(ARCH)  -o t2p/t2p t2p/t2p.c

#install:
#	cp t2p/t2p bin/t2p

clean:
	rm -f t2p/t2p

test:
	t2p/t2p -transcribe data/cmudict.0.7a.tree data/t2pin.tmp