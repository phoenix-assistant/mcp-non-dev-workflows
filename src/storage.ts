import Database from 'better-sqlite3';
import { join, dirname } from 'path';
import { existsSync, mkdirSync } from 'fs';
import { homedir } from 'os';

let db: Database.Database;

export function getDb(dbPath?: string): Database.Database {
  if (db) return db;
  let file: string;
  if (dbPath?.endsWith('.db')) {
    file = dbPath;
    const parent = dirname(file);
    if (!existsSync(parent)) mkdirSync(parent, { recursive: true });
  } else {
    const dir = dbPath || join(homedir(), '.mcp-workflows');
    if (!existsSync(dir)) mkdirSync(dir, { recursive: true });
    file = join(dir, 'data.db');
  }
  db = new Database(file);
  db.pragma('journal_mode = WAL');
  db.pragma('foreign_keys = ON');
  initTables(db);
  return db;
}

function initTables(db: Database.Database) {
  db.exec(`
    CREATE TABLE IF NOT EXISTS compliance_checklists (
      id TEXT PRIMARY KEY,
      name TEXT NOT NULL,
      template TEXT,
      status TEXT DEFAULT 'active',
      created_at TEXT DEFAULT (datetime('now')),
      updated_at TEXT DEFAULT (datetime('now'))
    );
    CREATE TABLE IF NOT EXISTS compliance_items (
      id TEXT PRIMARY KEY,
      checklist_id TEXT NOT NULL REFERENCES compliance_checklists(id),
      description TEXT NOT NULL,
      status TEXT DEFAULT 'pending',
      assignee TEXT,
      due_date TEXT,
      notes TEXT,
      updated_at TEXT DEFAULT (datetime('now'))
    );
    CREATE TABLE IF NOT EXISTS deals (
      id TEXT PRIMARY KEY,
      name TEXT NOT NULL,
      company TEXT,
      value REAL DEFAULT 0,
      stage TEXT DEFAULT 'prospecting',
      owner TEXT,
      created_at TEXT DEFAULT (datetime('now')),
      updated_at TEXT DEFAULT (datetime('now'))
    );
    CREATE TABLE IF NOT EXISTS deal_notes (
      id TEXT PRIMARY KEY,
      deal_id TEXT NOT NULL REFERENCES deals(id),
      content TEXT NOT NULL,
      author TEXT,
      created_at TEXT DEFAULT (datetime('now'))
    );
    CREATE TABLE IF NOT EXISTS tickets (
      id TEXT PRIMARY KEY,
      title TEXT NOT NULL,
      description TEXT,
      priority TEXT DEFAULT 'medium',
      status TEXT DEFAULT 'open',
      assignee TEXT,
      customer TEXT,
      escalation_level INTEGER DEFAULT 0,
      resolution TEXT,
      created_at TEXT DEFAULT (datetime('now')),
      updated_at TEXT DEFAULT (datetime('now'))
    );
  `);
}

export function closeDb() {
  if (db) { db.close(); }
}
