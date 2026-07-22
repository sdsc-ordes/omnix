<p align="center">
  <img src="./docs/assets/logo.svg" alt="project logo" width="250">
</p>

<h1 align="center">
    omnix
</h1>
<p align="center">
</p>


[![Current Release](https://img.shields.io/github/release/swissdatasciencecenter/omnix.svg?label=release)](https://github.com/sdsc-ordes/omnix/releases/latest)
[![Pipeline Status](https://img.shields.io/github/actions/workflow/status/sdsc-ordes/omnix/normal.yaml?label=ci)](https://github.com/sdsc-ordes/omnix/actions/workflows/normal.yaml)
[![License label](https://img.shields.io/badge/License-Apache2.0-blue.svg?)](http://www.apache.org/licenses/LICENSE-2.0.html)

## Usage

Copy `.example.env` to `.env` and fill in your SLIMS credentials. Then, whether you
installed with `pip`/`uv` or you're in the nix devshell (`direnv allow` / `just develop`):

```sh
omnix snapshot     # pull SLIMS -> build the local .omnix/snapshot.db  (add --limit N to sample)
omnix serve        # browse it at http://127.0.0.1:8000
```

The web app serves entirely from the local SQLite snapshot, so browsing needs no live
SLIMS access. Building a snapshot does reach your SLIMS instance over the network —
connect to its VPN first if it requires one (the EPFL instance does). `omnix dump`
prints raw records for debugging.

You get filterable tables of Tumors, Mice and Assays, drill-down from a tumor into its
linked mice and assays, and CSV/JSON export of the filtered set.
Re-run `omnix snapshot` to refresh.

`just snapshot` and `just serve` are convenience wrappers for the same commands.

## Development

Read first the [Contribution Guidelines](/CONTRIBUTING.md).

For technical documentation on setup and development, see the
[Development Guide](docs/development-guide.md)

## Acknowledgement

Acknowledge all contributors and external collaborators here.

## Copyright

Copyright © 2026-2028 Swiss Data Science Center (SDSC),
[www.datascience.ch](http://www.datascience.ch/). All rights reserved. The SDSC
is jointly established and legally represented by the École Polytechnique
Fédérale de Lausanne (EPFL) and the Eidgenössische Technische Hochschule Zürich
(ETH Zürich). This copyright encompasses all materials, software, documentation,
and other content created and developed by the SDSC.
