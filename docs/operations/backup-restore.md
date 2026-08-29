# Backup and restore

GoldGuard SQLite lives on the `/data` volume. Backups are hashed copies. Restore
never overwrites a nonempty target.

## Create a backup

From the app service, with the data volume mounted:

```bash
python scripts/backup_state.py --db /data/goldguard.db --out /data/backups/goldguard.backup
```

This writes the archive and a sibling `.sha256` file. The encryption passphrase
is operator-owned and is not stored in the archive.

## Restore into an empty target

```bash
python scripts/restore_state.py --archive /data/backups/goldguard.backup --target /tmp/restore-check.db
```

Restore refuses:

- a target that already has bytes
- a missing archive
- a payload whose SHA-256 does not match the sidecar
- a payload marked corrupt

Do not restore onto the live `/data/goldguard.db` while the writer replica is
running. Restore into a temporary empty path, verify, then swap during a
maintenance window.

## What is not in the backup

- Binance API secrets
- Telegram bot token
- Session / TOTP material
- OpenCodex provider tokens

Those stay in Railway secrets. Hermes `/opt/data` and OpenCodex `/app/.opencodex`
are separate volumes with their own backup schedules.
