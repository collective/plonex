# Database backup and recovery

`plonex db backup` makes an offline snapshot containing a full repozo backup of
`var/filestorage/Data.fs` and a copy of the configured blob storage. It holds the
FileStorage lock throughout the snapshot, verifies the repozo repository, and
records SHA-256 checksums for the blob files. The backup is published under
`var/backups/` only after all steps succeed.

Stop ZEO and any other FileStorage writers before backup. Coordinate any other
processes or hosts that can write directly to the blob storage: the FileStorage
lock cannot control them. A blob store changing during the copy fails the backup.
Snapshotting requires an existing blob directory and does not support symbolic
links inside it. The default implementation is for this project's local
FileStorage; it does not back up a remote database or additional storages.

```sh
plonex supervisor stop
plonex db backup
plonex db restore --to /path/to/new-recovery-directory
# Or choose a particular snapshot:
plonex db restore --from /path/to/snapshot --to /path/to/new-recovery-directory
```

Restore verifies the blob checksums and uses repozo's verify-on-recovery mode. It
writes `Data.fs` and `blobstorage/` into a **new** directory. It refuses an existing
destination and never replaces the live database. Inspect and test the recovered
site before arranging a separate, deliberate cutover while the relevant services
are stopped. A failed publish can leave the newly created recovery directory for
inspection.

Legacy repozo repositories under `var/backup/` do not contain the new snapshot
manifest or coordinated blobs. They are not automatically converted or selected
by this command. Recover those using repozo and their separately managed blob
backups according to the original backup procedure.

Test restores regularly and copy snapshots to storage independent of the server.
Snapshot checksums detect accidental corruption; they do not authenticate backups.
