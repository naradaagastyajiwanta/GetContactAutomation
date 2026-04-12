/**
 * Type Safety Tests
 *
 * Tests for:
 * - LID (Linked Identity) resolution fallback
 * - Type validation and coercion
 * - Message key handling
 * - Phone number normalization edge cases
 */

import {
  jest,
  describe,
  beforeEach,
  afterEach,
  it,
  expect,
} from "@jest/globals";
import { proto } from "@whiskeysockets/baileys";
import {
  createMockMessage,
  createLIDMessage,
  MockBaileysSocket,
  messageKeysEqual,
} from "./utils/mocks";

// Phone normalization implementation (matching the main service)
function normalizePhone(phone: string): string {
  let normalized = phone.trim();

  // Remove @s.whatsapp.net if already present
  if (normalized.includes("@")) {
    normalized = normalized.split("@")[0];
  }

  // Remove leading '+'
  if (normalized.startsWith("+")) {
    normalized = normalized.slice(1);
  }

  // Replace leading '0' with country code '62' (Indonesia)
  if (normalized.startsWith("0")) {
    normalized = "62" + normalized.slice(1);
  }

  return normalized + "@s.whatsapp.net";
}

// LID resolution implementation
interface LIDResolutionResult {
  success: boolean;
  phone?: string;
  fallbackUsed?: boolean;
  error?: string;
}

async function resolveLID(
  remoteJid: string,
  socket: MockBaileysSocket,
): Promise<LIDResolutionResult> {
  // Not a LID
  if (!remoteJid.endsWith("@lid")) {
    return {
      success: true,
      phone: remoteJid.split("@")[0].split(":")[0],
      fallbackUsed: false,
    };
  }

  // Try to resolve LID via Baileys
  try {
    const pn = await socket.signalRepository.lidMapping.getPNForLID(remoteJid);

    if (pn) {
      const phone = pn.split("@")[0].split(":")[0];
      return {
        success: true,
        phone,
        fallbackUsed: false,
      };
    }

    // LID resolution failed - try fallback
    return {
      success: false,
      error: "Could not resolve LID to phone number",
    };
  } catch (err) {
    return {
      success: false,
      error: (err as Error).message,
    };
  }
}

describe("Type Safety - Phone Number Normalization", () => {
  describe("Valid Phone Numbers", () => {
    it("should handle numbers with + prefix", () => {
      const result = normalizePhone("+6281234567890");
      expect(result).toBe("6281234567890@s.whatsapp.net");
    });

    it("should handle numbers without + prefix", () => {
      const result = normalizePhone("6281234567890");
      expect(result).toBe("6281234567890@s.whatsapp.net");
    });

    it("should handle numbers starting with 0", () => {
      const result = normalizePhone("081234567890");
      expect(result).toBe("6281234567890@s.whatsapp.net");
    });

    it("should handle numbers already with @s.whatsapp.net", () => {
      const result = normalizePhone("6281234567890@s.whatsapp.net");
      expect(result).toBe("6281234567890@s.whatsapp.net");
    });

    it("should handle numbers with + and domain", () => {
      const result = normalizePhone("+6281234567890@s.whatsapp.net");
      expect(result).toBe("6281234567890@s.whatsapp.net");
    });
  });

  describe("Edge Cases", () => {
    it("should handle numbers with spaces", () => {
      const result = normalizePhone(" 6281234567890 ");
      expect(result).toBe("6281234567890@s.whatsapp.net");
    });

    it("should handle numbers with device suffix", () => {
      const result = normalizePhone("6281234567890:1@s.whatsapp.net");
      expect(result).toBe("6281234567890@s.whatsapp.net");
    });

    it("should handle very short numbers", () => {
      const result = normalizePhone("08");
      expect(result).toBe("628@s.whatsapp.net");
    });

    it("should handle numbers with special characters in body", () => {
      // Only leading + should be removed
      const result = normalizePhone("6281234-5678-90");
      expect(result).toContain("6281234-5678-90@s.whatsapp.net");
    });

    it("should handle empty string gracefully", () => {
      const result = normalizePhone("");
      expect(result).toBe("@s.whatsapp.net");
    });

    it("should handle just the domain", () => {
      const result = normalizePhone("@s.whatsapp.net");
      expect(result).toBe("@s.whatsapp.net");
    });

    it("should handle numbers with multiple leading zeros", () => {
      const result = normalizePhone("00123456789");
      expect(result).toBe("6200123456789@s.whatsapp.net");
    });
  });

  describe("International Numbers", () => {
    it("should handle non-Indonesian numbers", () => {
      const result = normalizePhone("+1234567890");
      expect(result).toBe("1234567890@s.whatsapp.net");
    });

    it("should not modify non-zero-leading international numbers", () => {
      const result = normalizePhone("6512345678");
      expect(result).toBe("6512345678@s.whatsapp.net");
    });
  });
});

describe("Type Safety - LID Resolution", () => {
  let mockSocket: MockBaileysSocket;

  beforeEach(() => {
    mockSocket = new MockBaileysSocket();
  });

  describe("Successful LID Resolution", () => {
    it("should resolve LID to phone number successfully", async () => {
      const lid = "1234567890@lid";
      const resolvedPhone = "6281234567890@s.whatsapp.net";

      mockSocket.signalRepository.lidMapping.getPNForLID.mockResolvedValue(
        resolvedPhone,
      );

      const result = await resolveLID(lid, mockSocket);

      expect(result.success).toBe(true);
      expect(result.phone).toBe("6281234567890");
      expect(result.fallbackUsed).toBe(false);
      expect(
        mockSocket.signalRepository.lidMapping.getPNForLID,
      ).toHaveBeenCalledWith(lid);
    });

    it("should handle LID with device suffix in resolved phone", async () => {
      const lid = "1234567890@lid";
      const resolvedPhone = "6281234567890:5@s.whatsapp.net";

      mockSocket.signalRepository.lidMapping.getPNForLID.mockResolvedValue(
        resolvedPhone,
      );

      const result = await resolveLID(lid, mockSocket);

      expect(result.success).toBe(true);
      expect(result.phone).toBe("6281234567890");
    });
  });

  describe("Failed LID Resolution", () => {
    it("should return failure when LID not found", async () => {
      const lid = "unresolvable@lid";

      mockSocket.signalRepository.lidMapping.getPNForLID.mockResolvedValue(
        null,
      );

      const result = await resolveLID(lid, mockSocket);

      expect(result.success).toBe(false);
      expect(result.phone).toBeUndefined();
      expect(result.error).toContain("Could not resolve LID");
    });

    it("should handle LID resolution errors", async () => {
      const lid = "error@lid";

      mockSocket.signalRepository.lidMapping.getPNForLID.mockRejectedValue(
        new Error("Network error"),
      );

      const result = await resolveLID(lid, mockSocket);

      expect(result.success).toBe(false);
      expect(result.error).toContain("Network error");
    });

    it("should handle timeout during LID resolution", async () => {
      const lid = "timeout@lid";

      mockSocket.signalRepository.lidMapping.getPNForLID.mockImplementation(
        () =>
          new Promise((_, reject) =>
            setTimeout(() => reject(new Error("Timeout")), 100),
          ),
      );

      const resultPromise = resolveLID(lid, mockSocket);

      jest.advanceTimersByTime(150);

      const result = await resultPromise;

      expect(result.success).toBe(false);
      expect(result.error).toContain("Timeout");
    });
  });

  describe("Non-LID Handling", () => {
    it("should extract phone from regular JID", async () => {
      const regularJid = "6281234567890@s.whatsapp.net";

      const result = await resolveLID(regularJid, mockSocket);

      expect(result.success).toBe(true);
      expect(result.phone).toBe("6281234567890");
      expect(result.fallbackUsed).toBe(false);
      expect(
        mockSocket.signalRepository.lidMapping.getPNForLID,
      ).not.toHaveBeenCalled();
    });

    it("should extract phone from JID with device suffix", async () => {
      const jidWithDevice = "6281234567890:3@s.whatsapp.net";

      const result = await resolveLID(jidWithDevice, mockSocket);

      expect(result.success).toBe(true);
      expect(result.phone).toBe("6281234567890");
    });

    it("should handle group JID", async () => {
      const groupJid = "6281234567890-1234567@g.us";

      const result = await resolveLID(groupJid, mockSocket);

      expect(result.success).toBe(true);
      expect(result.phone).toBe("6281234567890-1234567");
    });
  });
});

describe("Type Safety - Message Key Handling", () => {
  describe("Message Key Equality", () => {
    it("should return true for identical keys", () => {
      const key1: proto.IMessageKey = {
        id: "msg123",
        remoteJid: "6281234567890@s.whatsapp.net",
        fromMe: false,
      };

      const key2: proto.IMessageKey = {
        id: "msg123",
        remoteJid: "6281234567890@s.whatsapp.net",
        fromMe: false,
      };

      expect(messageKeysEqual(key1, key2)).toBe(true);
    });

    it("should return false for different IDs", () => {
      const key1: proto.IMessageKey = {
        id: "msg123",
        remoteJid: "6281234567890@s.whatsapp.net",
        fromMe: false,
      };

      const key2: proto.IMessageKey = {
        id: "msg456",
        remoteJid: "6281234567890@s.whatsapp.net",
        fromMe: false,
      };

      expect(messageKeysEqual(key1, key2)).toBe(false);
    });

    it("should return false for different remote JIDs", () => {
      const key1: proto.IMessageKey = {
        id: "msg123",
        remoteJid: "628111111111@s.whatsapp.net",
        fromMe: false,
      };

      const key2: proto.IMessageKey = {
        id: "msg123",
        remoteJid: "628222222222@s.whatsapp.net",
        fromMe: false,
      };

      expect(messageKeysEqual(key1, key2)).toBe(false);
    });

    it("should return false for different fromMe values", () => {
      const key1: proto.IMessageKey = {
        id: "msg123",
        remoteJid: "6281234567890@s.whatsapp.net",
        fromMe: true,
      };

      const key2: proto.IMessageKey = {
        id: "msg123",
        remoteJid: "6281234567890@s.whatsapp.net",
        fromMe: false,
      };

      expect(messageKeysEqual(key1, key2)).toBe(false);
    });

    it("should handle null/undefined keys", () => {
      const key: proto.IMessageKey = {
        id: "msg123",
        remoteJid: "6281234567890@s.whatsapp.net",
        fromMe: false,
      };

      expect(messageKeysEqual(null, null)).toBe(true);
      expect(messageKeysEqual(undefined, undefined)).toBe(true);
      expect(messageKeysEqual(key, null)).toBe(false);
      expect(messageKeysEqual(null, key)).toBe(false);
    });

    it("should handle keys with missing optional fields", () => {
      const key1: proto.IMessageKey = {
        id: "msg123",
        remoteJid: "6281234567890@s.whatsapp.net",
      };

      const key2: proto.IMessageKey = {
        id: "msg123",
        remoteJid: "6281234567890@s.whatsapp.net",
        fromMe: false,
      };

      // fromMe defaults to undefined, which should differ from false
      expect(messageKeysEqual(key1, key2)).toBe(false);
    });
  });

  describe("Message Key Validation", () => {
    it("should identify valid message keys", () => {
      const validKey: proto.IMessageKey = {
        id: "msg123",
        remoteJid: "6281234567890@s.whatsapp.net",
        fromMe: false,
      };

      const isValid = validKey.id && validKey.remoteJid;
      expect(isValid).toBe(true);
    });

    it("should identify invalid message keys", () => {
      const invalidKey1: proto.IMessageKey = {
        id: "",
        remoteJid: "6281234567890@s.whatsapp.net",
        fromMe: false,
      };

      const invalidKey2: proto.IMessageKey = {
        id: "msg123",
        remoteJid: "",
        fromMe: false,
      };

      expect(invalidKey1.id && invalidKey1.remoteJid).toBe(false);
      expect(invalidKey2.id && invalidKey2.remoteJid).toBe(false);
    });

    it("should handle undefined fields", () => {
      const key: proto.IMessageKey = {
        id: undefined,
        remoteJid: undefined,
      };

      const hasRequiredFields = !!(key.id && key.remoteJid);
      expect(hasRequiredFields).toBe(false);
    });
  });
});

describe("Type Safety - Message Payload Validation", () => {
  describe("Send Message Payload", () => {
    it("should validate required fields", () => {
      const validPayload = {
        to: "6281234567890",
        message: "Hello world",
      };

      const hasRequired = validPayload.to && validPayload.message;
      expect(hasRequired).toBe(true);
    });

    it('should detect missing "to" field', () => {
      const invalidPayload: Record<string, string> = {
        message: "Hello world",
      };

      const hasRequired = invalidPayload.to && invalidPayload.message;
      expect(hasRequired).toBeFalsy();
    });

    it('should detect missing "message" field', () => {
      const invalidPayload: Record<string, string> = {
        to: "6281234567890",
      };

      const hasRequired = invalidPayload.to && invalidPayload.message;
      expect(hasRequired).toBeFalsy();
    });

    it("should handle empty strings", () => {
      const emptyPayload = {
        to: "",
        message: "",
      };

      const hasRequired = emptyPayload.to && emptyPayload.message;
      expect(hasRequired).toBe(false);
    });

    it("should accept optional replyToMsgKey", () => {
      const payload = {
        to: "6281234567890",
        message: "Reply",
        replyToMsgKey: {
          remoteJid: "6281234567890@s.whatsapp.net",
          id: "msg123",
          fromMe: false,
        },
      };

      expect(payload.to).toBeDefined();
      expect(payload.message).toBeDefined();
      expect(payload.replyToMsgKey).toBeDefined();
    });

    it("should accept optional allMsgKeys array", () => {
      const payload = {
        to: "6281234567890",
        message: "Reply to all",
        allMsgKeys: [
          {
            remoteJid: "6281234567890@s.whatsapp.net",
            id: "msg1",
            fromMe: false,
          },
          {
            remoteJid: "6281234567890@s.whatsapp.net",
            id: "msg2",
            fromMe: false,
          },
        ],
      };

      expect(Array.isArray(payload.allMsgKeys)).toBe(true);
      expect(payload.allMsgKeys?.length).toBe(2);
    });
  });

  describe("Webhook Payload Validation", () => {
    it("should validate webhook payload structure", () => {
      const webhookPayload = {
        from: "6281234567890",
        message: "Received message",
        timestamp: 1234567890,
        messageId: "msg123",
        pushName: "Test User",
        msgKey: {
          remoteJid: "6281234567890@s.whatsapp.net",
          id: "msg123",
          fromMe: false,
        },
      };

      expect(webhookPayload.from).toBeTruthy();
      expect(webhookPayload.message).toBeTruthy();
      expect(typeof webhookPayload.timestamp).toBe("number");
      expect(webhookPayload.msgKey?.id).toBeTruthy();
    });

    it("should handle optional allMsgKeys in webhook", () => {
      const webhookPayload = {
        from: "6281234567890",
        message: "Combined messages",
        timestamp: 1234567890,
        messageId: "msg123",
        pushName: "Test User",
        allMsgKeys: [
          {
            remoteJid: "6281234567890@s.whatsapp.net",
            id: "msg1",
            fromMe: false,
          },
          {
            remoteJid: "6281234567890@s.whatsapp.net",
            id: "msg2",
            fromMe: false,
          },
        ],
      };

      expect(Array.isArray(webhookPayload.allMsgKeys)).toBe(true);
    });
  });
});

describe("Type Safety - TypeScript Type Guards", () => {
  it("should narrow message types correctly", () => {
    const message: proto.IMessage = {
      conversation: "Text message",
    };

    const isConversationMessage = !!message.conversation;
    const isExtendedTextMessage = !!message.extendedTextMessage?.text;

    expect(isConversationMessage).toBe(true);
    expect(isExtendedTextMessage).toBe(false);
  });

  it("should detect vCard messages", () => {
    const vCardMessage: proto.IMessage = {
      contactMessage: {
        displayName: "John Doe",
        vcard: "BEGIN:VCARD\nVERSION:3.0\nFN:John\nEND:VCARD",
      },
    };

    const isVCard = !!vCardMessage.contactMessage?.vcard;
    expect(isVCard).toBe(true);
  });

  it("should detect contacts array messages", () => {
    const contactsArrayMessage: proto.IMessage = {
      contactsArrayMessage: {
        contacts: [
          {
            vcard: "BEGIN:VCARD\nVERSION:3.0\nFN:John\nEND:VCARD",
          },
        ],
      },
    };

    const isContactsArray =
      !!contactsArrayMessage.contactsArrayMessage?.contacts;
    expect(isContactsArray).toBe(true);
  });

  it("should handle empty message", () => {
    const emptyMessage: proto.IMessage = {};

    const hasContent = !!(
      emptyMessage.conversation ||
      emptyMessage.extendedTextMessage ||
      emptyMessage.contactMessage ||
      emptyMessage.contactsArrayMessage
    );

    expect(hasContent).toBe(false);
  });
});
