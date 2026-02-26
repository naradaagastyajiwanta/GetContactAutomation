/**
 * Test utilities for creating fake messages and mocking Baileys socket
 */

import { proto } from '@whiskeysockets/baileys';

export interface MockMessageOptions {
  remoteJid?: string;
  fromMe?: boolean;
  text?: string;
  pushName?: string;
  timestamp?: number;
  messageId?: string;
  isVCard?: boolean;
  vCardData?: string;
}

/**
 * Create a fake Baileys message for testing
 */
export function createMockMessage(options: MockMessageOptions = {}): proto.IWebMessageInfo {
  const {
    remoteJid = '6281234567890@s.whatsapp.net',
    fromMe = false,
    text = 'Hello world',
    pushName = 'Test User',
    timestamp = Math.floor(Date.now() / 1000),
    messageId = `msg_${Date.now()}`,
    isVCard = false,
    vCardData,
  } = options;

  const message: proto.IMessage = isVCard
    ? {
        contactMessage: {
          displayName: pushName,
          vcard: vCardData || `BEGIN:VCARD\nVERSION:3.0\nFN:${pushName}\nTEL;TYPE=CELL:+628123456789\nEND:VCARD`,
        },
      }
    : {
        conversation: text,
      };

  return {
    key: {
      remoteJid,
      fromMe,
      id: messageId,
      participant: undefined,
    },
    message,
    messageTimestamp: timestamp,
    pushName,
  };
}

/**
 * Create a fake LID message for testing Linked Identity resolution
 */
export function createLIDMessage(lid: string, text: string): proto.IWebMessageInfo {
  return createMockMessage({
    remoteJid: lid,
    fromMe: false,
    text,
  });
}

/**
 * Create a fake vCard message with multiple contacts
 */
export function createVCardArrayMessage(
  contacts: Array<{ name: string; phone: string }>
): proto.IWebMessageInfo {
  const vCards = contacts.map(
    (c) => `BEGIN:VCARD\nVERSION:3.0\nFN:${c.name}\nTEL;TYPE=CELL:${c.phone}\nEND:VCARD`
  );

  return {
    key: {
      remoteJid: '6281234567890@s.whatsapp.net',
      fromMe: false,
      id: `msg_${Date.now()}`,
    },
    message: {
      contactsArrayMessage: {
        contacts: vCards.map((vcard) => ({
          vcard,
          displayName: '',
        })),
      },
    },
    messageTimestamp: Math.floor(Date.now() / 1000),
    pushName: 'Test User',
  };
}

/**
 * Mock Baileys socket with minimal required methods
 */
export class MockBaileysSocket {
  public ev = {
    on: jest.fn(),
    removeAllListeners: jest.fn(),
    emit: jest.fn(),
  };

  public user = {
    id: '6281234567890:1@s.whatsapp.net',
  };

  public sendMessage = jest.fn().mockResolvedValue({
    key: { id: `sent_${Date.now()}`, remoteJid: '6281234567890@s.whatsapp.net' },
  });

  public sendPresenceUpdate = jest.fn().mockResolvedValue(undefined);

  public readMessages = jest.fn().mockResolvedValue(undefined);

  public logout = jest.fn().mockResolvedValue(undefined);

  public end = jest.fn().mockResolvedValue(undefined);

  public signalRepository = {
    lidMapping: {
      getPNForLID: jest.fn(),
    },
  };
}

/**
 * Mock Express request for testing API endpoints
 */
export function createMockRequest(body: any, params?: any): any {
  return {
    body,
    params,
    query: {},
  };
}

/**
 * Mock Express response for testing API endpoints
 */
export function createMockResponse(): any {
  const res: any = {
    status: jest.fn().mockReturnThis(),
    json: jest.fn().mockReturnThis(),
    send: jest.fn().mockReturnThis(),
  };
  return res;
}

/**
 * Wait for all pending promises to resolve
 */
export function flushPromises(): Promise<void> {
  return new Promise((resolve) => setImmediate(resolve));
}

/**
 * Create a mock webhook payload
 */
export function createWebhookPayload(options: {
  from?: string;
  message?: string;
  timestamp?: number;
  messageId?: string;
  pushName?: string;
}) {
  const {
    from = '6281234567890',
    message = 'Test message',
    timestamp = Math.floor(Date.now() / 1000),
    messageId = `msg_${Date.now()}`,
    pushName = 'Test User',
  } = options;

  return {
    from,
    message,
    timestamp,
    messageId,
    pushName,
    msgKey: {
      remoteJid: `${from}@s.whatsapp.net`,
      id: messageId,
      fromMe: false,
    },
  };
}

/**
 * Mock Axios for testing webhook calls
 */
export class MockAxiosInstance {
  public post = jest.fn();

  constructor() {
    this.post.mockResolvedValue({ data: { success: true } });
  }

  /**
   * Reset all mocks
   */
  resetMock(): void {
    this.post.mockReset();
  }

  /**
   * Set mock implementation for post
   */
  setPostImplementation(fn: () => any): void {
    this.post.mockImplementation(fn);
  }

  /**
   * Set mock rejection for post
   */
  setPostReject(error: Error): void {
    this.post.mockRejectedValue(error);
  }
}

/**
 * Type for pending message entry (mirrors implementation)
 */
export interface PendingMessageEntry {
  messages: string[];
  timer: ReturnType<typeof setTimeout>;
  firstMsgKey: proto.IMessageKey | null;
  allMsgKeys: proto.IMessageKey[];
  pushName: string;
  firstTimestamp: number;
}

/**
 * Helper to check if two message keys are equal
 */
export function messageKeysEqual(
  a: proto.IMessageKey | null | undefined,
  b: proto.IMessageKey | null | undefined
): boolean {
  if (!a && !b) return true;
  if (!a || !b) return false;
  return a.id === b.id && a.remoteJid === b.remoteJid && a.fromMe === b.fromMe;
}
