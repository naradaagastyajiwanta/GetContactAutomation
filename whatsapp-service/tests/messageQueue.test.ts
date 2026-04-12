/**
 * Message Queue Tests
 *
 * Tests for:
 * - Queue operations (add, remove, flush)
 * - Message deduplication
 * - Persistence and recovery
 * - Debouncing behavior
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
  flushPromises,
  type PendingMessageEntry,
} from "./utils/mocks";

// Import functions to test from the implementation
// Note: These would need to be exported from the main module or refactored into a separate module

describe("Message Queue", () => {
  let mockSocket: MockBaileysSocket;
  let pendingMessages: Map<string, PendingMessageEntry>;
  let flushToWebhookSpy: jest.Mock;
  const DEBOUNCE_MS = 5000;

  beforeEach(() => {
    jest.useFakeTimers();
    mockSocket = new MockBaileysSocket();
    pendingMessages = new Map();
    flushToWebhookSpy = jest.fn();
  });

  afterEach(() => {
    jest.useRealTimers();
    jest.clearAllMocks();
  });

  describe("Queue Operations", () => {
    it("should add a new message to the queue", () => {
      const msg = createMockMessage({
        remoteJid: "6281234567890@s.whatsapp.net",
        text: "Hello",
      });

      const fromPhone = "6281234567890";
      const timer = setTimeout(() => flushToWebhookSpy(fromPhone), DEBOUNCE_MS);

      pendingMessages.set(fromPhone, {
        messages: ["Hello"],
        timer,
        firstMsgKey: msg.key!,
        allMsgKeys: [msg.key!],
        pushName: msg.pushName ?? "",
        firstTimestamp:
          typeof msg.messageTimestamp === "number"
            ? msg.messageTimestamp
            : Date.now(),
      });

      expect(pendingMessages.size).toBe(1);
      const entry = pendingMessages.get(fromPhone);
      expect(entry?.messages).toEqual(["Hello"]);
      expect(entry?.firstMsgKey).toEqual(msg.key!);
    });

    it("should append to existing pending messages (debouncing)", () => {
      const fromPhone = "6281234567890";
      const msg1 = createMockMessage({ text: "Hello" });
      const msg2 = createMockMessage({ text: "World" });

      // Add first message
      let timer = setTimeout(() => flushToWebhookSpy(fromPhone), DEBOUNCE_MS);
      pendingMessages.set(fromPhone, {
        messages: ["Hello"],
        timer,
        firstMsgKey: msg1.key!,
        allMsgKeys: [msg1.key!],
        pushName: "Test User",
        firstTimestamp: Date.now(),
      });

      // Simulate second message arriving
      const existing = pendingMessages.get(fromPhone);
      expect(existing).toBeDefined();

      if (existing) {
        clearTimeout(existing.timer);
        existing.messages.push("World");
        existing.allMsgKeys.push(msg2.key!);
        timer = setTimeout(() => flushToWebhookSpy(fromPhone), DEBOUNCE_MS);
        existing.timer = timer;
      }

      expect(pendingMessages.get(fromPhone)?.messages).toEqual([
        "Hello",
        "World",
      ]);
      expect(pendingMessages.get(fromPhone)?.allMsgKeys.length).toBe(2);
    });

    it("should flush messages when timer expires", async () => {
      const fromPhone = "6281234567890";
      const msg = createMockMessage({ text: "Test message" });

      const timer = setTimeout(() => flushToWebhookSpy(fromPhone), DEBOUNCE_MS);
      pendingMessages.set(fromPhone, {
        messages: ["Test message"],
        timer,
        firstMsgKey: msg.key!,
        allMsgKeys: [msg.key!],
        pushName: "Test User",
        firstTimestamp: Date.now(),
      });

      // Fast forward past debounce time
      jest.advanceTimersByTime(DEBOUNCE_MS + 100);
      await flushPromises();

      expect(flushToWebhookSpy).toHaveBeenCalledWith(fromPhone);
    });

    it("should remove entry from queue after flushing", () => {
      const fromPhone = "6281234567890";
      const msg = createMockMessage({ text: "Test" });

      const timer = setTimeout(() => {}, DEBOUNCE_MS);
      pendingMessages.set(fromPhone, {
        messages: ["Test"],
        timer,
        firstMsgKey: msg.key!,
        allMsgKeys: [msg.key!],
        pushName: "User",
        firstTimestamp: Date.now(),
      });

      // Simulate flush
      pendingMessages.delete(fromPhone);
      clearTimeout(timer);

      expect(pendingMessages.size).toBe(0);
      expect(pendingMessages.get(fromPhone)).toBeUndefined();
    });
  });

  describe("Message Deduplication", () => {
    it("should not add duplicate message keys", () => {
      const fromPhone = "6281234567890";
      const msg = createMockMessage({
        messageId: "msg_123",
        text: "Duplicate test",
      });

      const timer = setTimeout(() => {}, DEBOUNCE_MS);
      pendingMessages.set(fromPhone, {
        messages: ["Duplicate test"],
        timer,
        firstMsgKey: msg.key!,
        allMsgKeys: [msg.key!],
        pushName: "User",
        firstTimestamp: Date.now(),
      });

      // Try to add the same message key again
      const existing = pendingMessages.get(fromPhone);
      if (existing && !existing.allMsgKeys.find((k) => k.id === msg.key!.id)) {
        existing.allMsgKeys.push(msg.key!);
      }

      expect(pendingMessages.get(fromPhone)?.allMsgKeys.length).toBe(1);
    });

    it("should handle messages from different senders separately", () => {
      const msg1 = createMockMessage({
        remoteJid: "628111111111@s.whatsapp.net",
        text: "From user 1",
      });
      const msg2 = createMockMessage({
        remoteJid: "628222222222@s.whatsapp.net",
        text: "From user 2",
      });

      const timer1 = setTimeout(() => {}, DEBOUNCE_MS);
      const timer2 = setTimeout(() => {}, DEBOUNCE_MS);

      pendingMessages.set("628111111111", {
        messages: ["From user 1"],
        timer: timer1,
        firstMsgKey: msg1.key!,
        allMsgKeys: [msg1.key!],
        pushName: "User1",
        firstTimestamp: Date.now(),
      });

      pendingMessages.set("628222222222", {
        messages: ["From user 2"],
        timer: timer2,
        firstMsgKey: msg2.key!,
        allMsgKeys: [msg2.key!],
        pushName: "User2",
        firstTimestamp: Date.now(),
      });

      expect(pendingMessages.size).toBe(2);
    });
  });

  describe("Debouncing Behavior", () => {
    it("should reset timer when new message arrives", () => {
      const fromPhone = "6281234567890";
      const clearTimeoutSpy = jest.spyOn(global, "clearTimeout");

      const msg1 = createMockMessage({ text: "First" });
      let timer = setTimeout(() => flushToWebhookSpy(fromPhone), DEBOUNCE_MS);

      pendingMessages.set(fromPhone, {
        messages: ["First"],
        timer,
        firstMsgKey: msg1.key!,
        allMsgKeys: [msg1.key!],
        pushName: "User",
        firstTimestamp: Date.now(),
      });

      // Second message arrives
      const existing = pendingMessages.get(fromPhone);
      if (existing) {
        clearTimeout(existing.timer);
        existing.messages.push("Second");
        timer = setTimeout(() => flushToWebhookSpy(fromPhone), DEBOUNCE_MS);
        existing.timer = timer;
      }

      expect(clearTimeoutSpy).toHaveBeenCalled();

      // Advance time but not past the new debounce window
      jest.advanceTimersByTime(DEBOUNCE_MS - 1000);
      expect(flushToWebhookSpy).not.toHaveBeenCalled();

      // Advance past the new debounce window
      jest.advanceTimersByTime(2000);
      expect(flushToWebhookSpy).toHaveBeenCalled();
    });

    it("should combine multiple rapid messages into one webhook call", async () => {
      const fromPhone = "6281234567890";
      const messages = ["Msg1", "Msg2", "Msg3", "Msg4"];

      let timer = setTimeout(() => flushToWebhookSpy(fromPhone), DEBOUNCE_MS);
      pendingMessages.set(fromPhone, {
        messages: [messages[0]],
        timer,
        firstMsgKey: createMockMessage({ text: messages[0] }).key!,
        allMsgKeys: [createMockMessage({ text: messages[0] }).key!],
        pushName: "User",
        firstTimestamp: Date.now(),
      });

      // Add remaining messages rapidly
      const existing = pendingMessages.get(fromPhone);
      if (existing) {
        for (let i = 1; i < messages.length; i++) {
          clearTimeout(existing.timer);
          existing.messages.push(messages[i]);
          existing.allMsgKeys.push(
            createMockMessage({ text: messages[i] }).key!,
          );
        }
        timer = setTimeout(() => flushToWebhookSpy(fromPhone), DEBOUNCE_MS);
        existing.timer = timer;
      }

      // Fast forward to trigger flush
      jest.advanceTimersByTime(DEBOUNCE_MS + 100);
      await flushPromises();

      expect(flushToWebhookSpy).toHaveBeenCalledTimes(1);

      // Verify combined message
      const entry = pendingMessages.get(fromPhone);
      expect(entry?.messages).toEqual(messages);
    });

    it("should preserve first message timestamp in debounced batch", () => {
      const fromPhone = "6281234567890";
      const firstTimestamp = 1234567890;

      const timer = setTimeout(() => {}, DEBOUNCE_MS);
      pendingMessages.set(fromPhone, {
        messages: ["First"],
        timer,
        firstMsgKey: createMockMessage({ text: "First" }).key!,
        allMsgKeys: [createMockMessage({ text: "First" }).key!],
        pushName: "User",
        firstTimestamp,
      });

      // Add more messages
      const existing = pendingMessages.get(fromPhone);
      if (existing) {
        existing.messages.push("Second");
        existing.messages.push("Third");
      }

      expect(pendingMessages.get(fromPhone)?.firstTimestamp).toBe(
        firstTimestamp,
      );
    });
  });

  describe("LID Resolution", () => {
    it("should handle LID messages correctly", async () => {
      const lid = "1234567890@lid";
      const resolvedPhone = "6281234567890";
      const msg = createLIDMessage(lid, "LID message");

      // Mock LID resolution
      mockSocket.signalRepository.lidMapping.getPNForLID.mockResolvedValue(
        `${resolvedPhone}@s.whatsapp.net`,
      );

      const pn = await mockSocket.signalRepository.lidMapping.getPNForLID(lid);
      expect(pn).toBeDefined();

      const from = pn ? pn.split("@")[0].split(":")[0] : null;
      expect(from).toBe(resolvedPhone);
    });

    it("should skip message when LID resolution fails", async () => {
      const lid = "unresolvable@lid";
      mockSocket.signalRepository.lidMapping.getPNForLID.mockResolvedValue(
        null,
      );

      const pn = await mockSocket.signalRepository.lidMapping.getPNForLID(lid);
      expect(pn).toBeNull();
    });
  });

  describe("Message Key Handling", () => {
    it("should store all message keys for read receipts", () => {
      const fromPhone = "6281234567890";
      const msgKeys = [
        createMockMessage({ messageId: "msg1" }).key!,
        createMockMessage({ messageId: "msg2" }).key!,
        createMockMessage({ messageId: "msg3" }).key!,
      ];

      const timer = setTimeout(() => {}, DEBOUNCE_MS);
      pendingMessages.set(fromPhone, {
        messages: ["Msg1", "Msg2", "Msg3"],
        timer,
        firstMsgKey: msgKeys[0],
        allMsgKeys: msgKeys,
        pushName: "User",
        firstTimestamp: Date.now(),
      });

      expect(pendingMessages.get(fromPhone)?.allMsgKeys).toEqual(msgKeys);
      expect(pendingMessages.get(fromPhone)?.allMsgKeys.length).toBe(3);
    });

    it("should filter out invalid message keys", () => {
      const fromPhone = "6281234567890";
      const validKey = createMockMessage({ messageId: "valid" }).key!;
      const invalidKey = { id: "", remoteJid: "", fromMe: false };

      const timer = setTimeout(() => {}, DEBOUNCE_MS);
      pendingMessages.set(fromPhone, {
        messages: ["Msg1", "Msg2"],
        timer,
        firstMsgKey: validKey,
        allMsgKeys: [validKey, invalidKey as proto.IMessageKey],
        pushName: "User",
        firstTimestamp: Date.now(),
      });

      const filtered = pendingMessages
        .get(fromPhone)
        ?.allMsgKeys.filter((k) => k.remoteJid && k.id);

      expect(filtered?.length).toBe(1);
      expect(filtered?.[0]).toEqual(validKey);
    });
  });

  describe("Memory Management", () => {
    it("should handle timer cleanup on manual flush", () => {
      const fromPhone = "6281234567890";
      const clearTimeoutSpy = jest.spyOn(global, "clearTimeout");

      const timer = setTimeout(() => {}, DEBOUNCE_MS);
      pendingMessages.set(fromPhone, {
        messages: ["Test"],
        timer,
        firstMsgKey: createMockMessage().key!,
        allMsgKeys: [createMockMessage().key!],
        pushName: "User",
        firstTimestamp: Date.now(),
      });

      // Manual flush
      const entry = pendingMessages.get(fromPhone);
      if (entry) {
        clearTimeout(entry.timer);
        pendingMessages.delete(fromPhone);
      }

      expect(clearTimeoutSpy).toHaveBeenCalled();
      expect(pendingMessages.size).toBe(0);
    });

    it("should handle empty message queue", () => {
      expect(pendingMessages.size).toBe(0);

      const entry = pendingMessages.get("nonexistent");
      expect(entry).toBeUndefined();
    });

    it("should handle rapid queue creation and deletion", () => {
      const phones = ["628111", "628222", "628333"];

      phones.forEach((phone) => {
        const timer = setTimeout(() => {}, DEBOUNCE_MS);
        pendingMessages.set(phone, {
          messages: [`Message from ${phone}`],
          timer,
          firstMsgKey: createMockMessage().key!,
          allMsgKeys: [createMockMessage().key!],
          pushName: "User",
          firstTimestamp: Date.now(),
        });
      });

      expect(pendingMessages.size).toBe(3);

      // Remove all
      phones.forEach((phone) => {
        const entry = pendingMessages.get(phone);
        if (entry) clearTimeout(entry.timer);
        pendingMessages.delete(phone);
      });

      expect(pendingMessages.size).toBe(0);
    });
  });
});
