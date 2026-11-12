-- Migration 001: first authentication detection slice. Apply once with the Supabase SQL editor.

-- Backend-only tables: no browser Data API access. Backend queries must authorize workspace membership.

BEGIN;

CREATE TABLE soc_workspaces (
	id VARCHAR(36) NOT NULL,
	name VARCHAR(100) NOT NULL,
	PRIMARY KEY (id)
);

ALTER TABLE public.soc_workspaces ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON TABLE public.soc_workspaces FROM anon, authenticated, PUBLIC;

CREATE TABLE soc_audit_logs (
	id VARCHAR(36) NOT NULL,
	workspace_id VARCHAR(36) NOT NULL,
	actor VARCHAR(100) NOT NULL,
	action VARCHAR(40) NOT NULL,
	target_id VARCHAR(36) NOT NULL,
	details JSON NOT NULL,
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(workspace_id) REFERENCES soc_workspaces (id)
);

CREATE INDEX ix_soc_audit_logs_workspace_id ON soc_audit_logs (workspace_id);

ALTER TABLE public.soc_audit_logs ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON TABLE public.soc_audit_logs FROM anon, authenticated, PUBLIC;

CREATE TABLE soc_incidents (
	id VARCHAR(36) NOT NULL,
	workspace_id VARCHAR(36) NOT NULL,
	title VARCHAR(200) NOT NULL,
	status VARCHAR(24) NOT NULL,
	severity VARCHAR(10) NOT NULL,
	risk_score INTEGER NOT NULL,
	score_components JSON NOT NULL,
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(workspace_id) REFERENCES soc_workspaces (id)
);

CREATE INDEX ix_soc_incidents_workspace_id ON soc_incidents (workspace_id);

ALTER TABLE public.soc_incidents ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON TABLE public.soc_incidents FROM anon, authenticated, PUBLIC;

CREATE TABLE soc_memberships (
	user_id VARCHAR(36) NOT NULL,
	workspace_id VARCHAR(36) NOT NULL,
	role VARCHAR(10) NOT NULL,
	PRIMARY KEY (user_id),
	FOREIGN KEY(workspace_id) REFERENCES soc_workspaces (id)
);

CREATE INDEX ix_soc_memberships_workspace_id ON soc_memberships (workspace_id);

ALTER TABLE public.soc_memberships ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON TABLE public.soc_memberships FROM anon, authenticated, PUBLIC;

CREATE TABLE soc_sources (
	id VARCHAR(36) NOT NULL,
	workspace_id VARCHAR(36) NOT NULL,
	name VARCHAR(100) NOT NULL,
	token_hash VARCHAR(64) NOT NULL,
	enabled BOOLEAN NOT NULL,
	last_seen TIMESTAMP WITHOUT TIME ZONE,
	PRIMARY KEY (id),
	FOREIGN KEY(workspace_id) REFERENCES soc_workspaces (id),
	UNIQUE (token_hash)
);

CREATE INDEX ix_soc_sources_workspace_id ON soc_sources (workspace_id);

ALTER TABLE public.soc_sources ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON TABLE public.soc_sources FROM anon, authenticated, PUBLIC;

CREATE TABLE soc_alerts (
	id VARCHAR(36) NOT NULL,
	workspace_id VARCHAR(36) NOT NULL,
	incident_id VARCHAR(36) NOT NULL,
	rule_key VARCHAR(40) NOT NULL,
	dedup_key VARCHAR(64) NOT NULL,
	explanation VARCHAR(500) NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(workspace_id) REFERENCES soc_workspaces (id),
	FOREIGN KEY(incident_id) REFERENCES soc_incidents (id),
	UNIQUE (dedup_key)
);

CREATE INDEX ix_soc_alerts_incident_id ON soc_alerts (incident_id);

CREATE INDEX ix_soc_alerts_workspace_id ON soc_alerts (workspace_id);

ALTER TABLE public.soc_alerts ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON TABLE public.soc_alerts FROM anon, authenticated, PUBLIC;

CREATE TABLE soc_events (
	id VARCHAR(36) NOT NULL,
	workspace_id VARCHAR(36) NOT NULL,
	source_id VARCHAR(36) NOT NULL,
	external_event_id VARCHAR(128) NOT NULL,
	event_time TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	ingested_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	event_type VARCHAR(32) NOT NULL,
	source_ip VARCHAR(45) NOT NULL,
	destination_ip VARCHAR(45) NOT NULL,
	destination_port INTEGER NOT NULL,
	username VARCHAR(128) NOT NULL,
	raw_data JSON NOT NULL,
	PRIMARY KEY (id),
	UNIQUE (source_id, external_event_id),
	FOREIGN KEY(workspace_id) REFERENCES soc_workspaces (id),
	FOREIGN KEY(source_id) REFERENCES soc_sources (id)
);

CREATE INDEX ix_soc_events_workspace_id ON soc_events (workspace_id);

CREATE INDEX soc_event_detection ON soc_events (workspace_id, source_id, event_type, event_time);

ALTER TABLE public.soc_events ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON TABLE public.soc_events FROM anon, authenticated, PUBLIC;

CREATE TABLE soc_alert_events (
	alert_id VARCHAR(36) NOT NULL,
	event_id VARCHAR(36) NOT NULL,
	PRIMARY KEY (alert_id, event_id),
	FOREIGN KEY(alert_id) REFERENCES soc_alerts (id),
	FOREIGN KEY(event_id) REFERENCES soc_events (id)
);

ALTER TABLE public.soc_alert_events ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON TABLE public.soc_alert_events FROM anon, authenticated, PUBLIC;

CREATE TABLE public.soc_schema_migrations (version INTEGER PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT now());

ALTER TABLE public.soc_schema_migrations ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON TABLE public.soc_schema_migrations FROM anon, authenticated, PUBLIC;

INSERT INTO public.soc_schema_migrations (version) VALUES (1);

COMMIT;
