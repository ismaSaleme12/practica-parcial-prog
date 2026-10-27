# Spec Delta

## Purpose

Provides the cryptographic primitives the authentication module will build on: password hashing that never blocks the event loop and signed tokens that carry an untruncated issue time, an expiry and the user identity.

## ADDED Requirements

### Requirement: Password hashing off the event loop

Password hashing and verification SHALL run outside the event loop under a bounded concurrency limit, using the configured bcrypt cost, and SHALL never expose the original password or allow a failing verification to raise.

#### Scenario: Hashing a password

- **WHEN** a password is hashed
- **THEN** the result is a bcrypt hash different from the input, using the cost declared in the configuration.

#### Scenario: Verifying a password

- **WHEN** a plain password is verified against its stored hash
- **THEN** the verification returns true, and it returns false for any other password.

#### Scenario: Verification of a malformed hash

- **WHEN** the stored value is not a valid bcrypt hash
- **THEN** the verification returns false instead of raising.

#### Scenario: Bounded concurrency

- **WHEN** more hash operations are requested at once than the configured concurrency limit
- **THEN** the extra operations wait for a free slot instead of running all at the same time.

### Requirement: Token issuance

The system SHALL issue a signed token carrying the user identity, the issue time with full resolution and an expiry taken from the configuration or from an explicit override, and SHALL sign it with the secret loaded from the environment.

#### Scenario: Default expiry

- **WHEN** a token is issued without an explicit duration
- **THEN** it expires after the duration declared in the configuration.

#### Scenario: Explicit expiry override

- **WHEN** a token is issued with an explicit duration
- **THEN** the expiry reflects that duration instead of the configured default.

#### Scenario: Untruncated issue time

- **WHEN** a token is issued
- **THEN** its `iat` claim preserves the issue time without being truncated to seconds, so sessions from the same second can be ordered against a password change.

### Requirement: Token verification

The system SHALL verify a token's signature, expiry and required claims, and SHALL reject it without raising when any check fails.

#### Scenario: Valid token

- **WHEN** a token issued by the system is verified
- **THEN** its claims are returned, including the user identity.

#### Scenario: Expired token

- **WHEN** a token whose expiry has passed is verified
- **THEN** the verification reports failure and returns no claims.

#### Scenario: Tampered or foreign token

- **WHEN** a token with an invalid signature, a different signing key or a missing required claim is verified
- **THEN** the verification reports failure and returns no claims.
