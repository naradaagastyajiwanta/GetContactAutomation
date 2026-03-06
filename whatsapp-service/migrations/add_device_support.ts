/**
 * WhatsApp Service Database Migration
 * Add Multi-Device Support
 *
 * This migration:
 * 1. Adds device_id column to message_queue table
 * 2. Creates devices table
 * 3. Inserts 5 default devices
 * 4. Updates existing messages to device_1
 *
 * Run: npx ts-node migrations/add_device_support.ts
 */

import Database from 'better-sqlite3';
import * as fs from 'fs';
import * as path from 'path';

const DB_PATH = path.join(__dirname, '..', 'data', 'message_queue.db');

console.log('Starting multi-device support migration...');
console.log(`Database: ${DB_PATH}`);

// Check if database exists
if (!fs.existsSync(DB_PATH)) {
  console.log('Database does not exist yet. It will be created with device support on next startup.');
  process.exit(0);
}

const db = new Database(DB_PATH);
db.pragma('journal_mode = WAL');

// Enable foreign keys
db.pragma('foreign_keys = ON');

console.log('Connected to database');

try {
  // Start transaction for atomic migration
  const migrate = db.transaction(() => {
    // Step 1: Check if device_id column already exists
    const tableInfo = db.pragma(`table_info('message_queue')`) as any[];
    const hasDeviceIdColumn = tableInfo.some((col: any) => col.name === 'device_id');

    if (!hasDeviceIdColumn) {
      console.log('Adding device_id column to message_queue table...');
      db.exec(`
        ALTER TABLE message_queue ADD COLUMN device_id TEXT DEFAULT 'device_1';
      `);
      console.log('✓ device_id column added');
    } else {
      console.log('✓ device_id column already exists');
    }

    // Step 2: Create devices table if not exists
    const deviceTableExists = db.prepare(`
      SELECT name FROM sqlite_master WHERE type='table' AND name='devices';
    `).get();

    if (!deviceTableExists) {
      console.log('Creating devices table...');
      db.exec(`
        CREATE TABLE devices (
          id TEXT PRIMARY KEY,
          name TEXT NOT NULL,
          phone_number TEXT,
          auth_store_path TEXT NOT NULL,
          enabled INTEGER DEFAULT 1
        );
      `);
      console.log('✓ devices table created');
    } else {
      console.log('✓ devices table already exists');
    }

    // Step 3: Check if devices already exist
    const existingDevices = db.prepare('SELECT COUNT(*) as count FROM devices').get() as { count: number };

    if (existingDevices.count === 0) {
      console.log('Inserting default devices...');

      const insertDevice = db.prepare(`
        INSERT INTO devices (id, name, auth_store_path, enabled)
        VALUES (?, ?, ?, 1)
      `);

      const devices = [
        { id: 'device_1', name: 'WhatsApp Device 1', authStorePath: path.join(__dirname, '..', 'auth_store_device_1') },
        { id: 'device_2', name: 'WhatsApp Device 2', authStorePath: path.join(__dirname, '..', 'auth_store_device_2') },
        { id: 'device_3', name: 'WhatsApp Device 3', authStorePath: path.join(__dirname, '..', 'auth_store_device_3') },
        { id: 'device_4', name: 'WhatsApp Device 4', authStorePath: path.join(__dirname, '..', 'auth_store_device_4') },
        { id: 'device_5', name: 'WhatsApp Device 5', authStorePath: path.join(__dirname, '..', 'auth_store_device_5') },
      ];

      for (const device of devices) {
        insertDevice.run(device.id, device.name, device.authStorePath);
        console.log(`  ✓ Inserted ${device.id}: ${device.name}`);
      }
    } else {
      console.log(`✓ ${existingDevices.count} devices already exist`);
    }

    // Step 4: Create index for device_id if not exists
    const indexExists = db.prepare(`
      SELECT name FROM sqlite_master WHERE type='index' AND name='idx_message_queue_device';
    `).get();

    if (!indexExists) {
      console.log('Creating index for device_id...');
      db.exec(`
        CREATE INDEX idx_message_queue_device ON message_queue(device_id);
      `);
      console.log('✓ idx_message_queue_device created');
    } else {
      console.log('✓ idx_message_queue_device already exists');
    }

    // Step 5: Update any NULL device_id values to 'device_1'
    const nullDeviceIds = db.prepare('SELECT COUNT(*) as count FROM message_queue WHERE device_id IS NULL').get() as { count: number };

    if (nullDeviceIds.count > 0) {
      console.log(`Updating ${nullDeviceIds.count} messages with NULL device_id to 'device_1'...`);
      db.exec(`
        UPDATE message_queue SET device_id = 'device_1' WHERE device_id IS NULL;
      `);
      console.log('✓ Messages updated');
    }
  });

  // Execute migration
  migrate();

  console.log('\n✅ Migration completed successfully!');
  console.log('\nNext steps:');
  console.log('1. Restart the whatsapp-service');
  console.log('2. Connect additional devices via the frontend Device Panel');
  console.log('3. Test bulk send with device selection');

} catch (error) {
  console.error('\n❌ Migration failed:', error);
  process.exit(1);
} finally {
  db.close();
}
