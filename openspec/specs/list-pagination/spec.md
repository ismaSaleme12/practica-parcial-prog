# list-pagination Specification

## Purpose
Defines how every list endpoint is paginated: one envelope shape, bounded page parameters, a total computed with the same filters as the page and a proper error when the requested page does not exist.

## Requirements

### Requirement: Uniform pagination envelope

Every paginated listing SHALL respond with a single envelope containing the page items, the total number of matching records, the requested page, the requested size and the number of available pages.

#### Scenario: First page of a listing

- **WHEN** a client requests a paginated listing without parameters
- **THEN** the response contains `items`, `total`, `page`, `size` and `pages`, with `page` starting at 1 and `size` defaulting to 20.

#### Scenario: Page slicing

- **WHEN** a listing with more records than the requested size is paginated
- **THEN** `items` contains at most `size` records of the requested page and `pages` equals the ceiling of `total` divided by `size`.

#### Scenario: Empty result

- **WHEN** a listing has no records matching its filters
- **THEN** the response contains an empty `items` list, `total` equal to 0 and `pages` equal to 0.

### Requirement: Bounded page parameters

The pagination parameters SHALL accept a page number starting at 1 and a page size between 1 and 100, and SHALL reject any value outside those bounds with a 422 response and a message of its own.

#### Scenario: Page below one

- **WHEN** a client requests page 0 or a negative page
- **THEN** the system responds 422 with a message describing the valid page range.

#### Scenario: Size out of range

- **WHEN** a client requests a size of 0, a negative size or a size greater than 100
- **THEN** the system responds 422 with a message describing the valid size range.

#### Scenario: Valid boundary values

- **WHEN** a client requests page 1 with size 1 or size 100
- **THEN** the request is accepted and the envelope echoes those values.

### Requirement: Total uses the same filters as the page

The total reported by a paginated listing SHALL be computed with exactly the same filters as the returned page, so `pages` never describes a different collection than `items`.

#### Scenario: Filtered listing

- **WHEN** a listing is filtered by a search term or any other criterion
- **THEN** `total` counts only the records matching that criterion and never the whole table.

#### Scenario: Page beyond the filtered total

- **WHEN** a client requests a page that is beyond the last page available for the applied filters
- **THEN** the system responds 422 with a message stating that the page does not exist and how many pages there are.
