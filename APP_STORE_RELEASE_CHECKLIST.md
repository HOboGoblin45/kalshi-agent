# App Store Release Checklist

## Product Quality

- [ ] UI validated on desktop and mobile layouts
- [ ] No visible encoding artifacts or broken text
- [ ] Error states are user-friendly (offline/backend down)
- [ ] 404 handling exists for invalid routes
- [ ] Loading/empty states are clear

## Reliability

- [ ] `pytest -q` passes
- [ ] `npm run check` passes
- [ ] Backend starts with `--dry-run` and dashboard is reachable
- [ ] Toggle controls and polling behavior verified manually

## Security

- [ ] Dashboard host is localhost for consumer builds
- [ ] Dashboard token is configured if non-local access is required
- [ ] Secrets are excluded from shipped package (`.env`, config keys)
- [ ] No plaintext credentials in repository

## Compliance

- [ ] Privacy policy included and linked from listing
- [ ] Financial risk disclaimer included in listing copy
- [ ] Support contact information added to listing
- [ ] Region/legal restrictions reviewed

## Store Assets

- [ ] App name, subtitle, and category finalized
- [ ] High-res icon and screenshots prepared
- [ ] Marketing description and keywords finalized
- [ ] Version and release notes updated

## Distribution

- [ ] Build reproducibility documented
- [ ] Install/start scripts verified on clean machine
- [ ] Rollback plan for critical release issues
