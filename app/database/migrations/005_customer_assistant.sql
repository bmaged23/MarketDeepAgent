CREATE TABLE IF NOT EXISTS customer_sessions (
    token_hash TEXT PRIMARY KEY,
    person_id INTEGER NOT NULL REFERENCES person(person_id),
    csrf_hash TEXT NOT NULL,
    expires_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS customer_preferences (
    person_id INTEGER PRIMARY KEY REFERENCES person(person_id),
    memory_enabled INTEGER NOT NULL DEFAULT 1 CHECK(memory_enabled IN (0,1))
);
CREATE TABLE IF NOT EXISTS conversations (
    conversation_id TEXT PRIMARY KEY,
    person_id INTEGER NOT NULL REFERENCES person(person_id),
    summary TEXT NOT NULL DEFAULT '',
    busy INTEGER NOT NULL DEFAULT 0,
    busy_at INTEGER,
    lock_token TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS conversation_messages (
    message_id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id TEXT NOT NULL REFERENCES conversations(conversation_id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK(role IN ('user','assistant')),
    content TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS customer_memories (
    memory_id INTEGER PRIMARY KEY AUTOINCREMENT,
    person_id INTEGER NOT NULL REFERENCES person(person_id),
    memory_key TEXT NOT NULL,
    text TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    active INTEGER NOT NULL DEFAULT 1,
    source_message_id INTEGER REFERENCES conversation_messages(message_id) ON DELETE SET NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(person_id,memory_key)
);
CREATE TABLE IF NOT EXISTS customer_memory_jobs (
    memory_id INTEGER PRIMARY KEY REFERENCES customer_memories(memory_id),
    version INTEGER NOT NULL,
    operation TEXT NOT NULL CHECK(operation IN ('upsert','delete')),
    status TEXT NOT NULL DEFAULT 'pending',
    error TEXT
);
CREATE INDEX IF NOT EXISTS ix_conversation_owner ON conversations(person_id);
CREATE INDEX IF NOT EXISTS ix_message_conversation ON conversation_messages(conversation_id,message_id);
CREATE INDEX IF NOT EXISTS ix_memory_owner_active ON customer_memories(person_id,active);
