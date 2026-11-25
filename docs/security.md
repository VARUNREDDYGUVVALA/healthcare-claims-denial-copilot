# Local demo security

The local Compose service binds to loopback. Use distinct analyst and supervisor tokens and keep them out of version control. Start and read investigations with either role. Only a supervisor can record a final review. The run and audit event are persisted together in DuckDB. The MCP server exposes evidence reads over stdio. The public Pages site contains fictional data and has no server API or role tokens.
