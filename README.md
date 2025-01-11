# Hello world

This is me!

## Autocomplete

Add something like this to your startup script:

```sh
eval "$(register-python-argcomplete plonex)"
```

## Initialize your project

You can initialize a new project with the `init` command:

```sh
$ plonex init foo
INFO     Creating foo/tmp
INFO     Creating foo/etc
INFO     Creating foo/var
INFO     Creating foo/var/blobstorage
INFO     Creating foo/var/cache
INFO     Creating foo/var/filestorage
INFO     Creating foo/var/log
INFO     Creating foo/etc/plonex.yml
INFO     Project initialized
```

## Install your packages

```sh
plonex dependencies
```

## Start your project

```sh
plonex supervisor start
```
