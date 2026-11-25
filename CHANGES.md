# Changelog

<!-- towncrier release notes start -->

## 0.0.1a2 (2026-11-25)


### New features

- Use `supervisor start`, `supervisor stop`, and `supervisor restart` with one or more program names to manage selected programs. Pass `all` to act on every managed program while keeping the Supervisor daemon running. 


### Bug fixes

- Resolve relative template service paths and local file URIs against the YAML file that defines them. Existing configurations using project-root-relative paths need to be updated. 

## 0.0.1a1 (2026-11-18)


### New features

- Support remote profiles 

## 0.0.1a0 (2026-11-15)

### Internal

- First alpha
