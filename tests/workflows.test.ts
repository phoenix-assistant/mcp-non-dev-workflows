import { describe, it, expect, beforeAll, afterAll } from 'vitest';
import { getDb, closeDb } from '../src/storage.js';
import * as compliance from '../src/workflows/compliance.js';
import * as dealflow from '../src/workflows/dealflow.js';
import * as support from '../src/workflows/support.js';
import { unlinkSync } from 'fs';

const TEST_DB = '/tmp/mcp-workflows-test.db';

beforeAll(() => { getDb(TEST_DB); });
afterAll(() => { closeDb(); try { unlinkSync(TEST_DB); } catch {} });

describe('compliance', () => {
  let checklistId: string;
  let itemId: string;

  it('creates checklist from template', () => {
    const result = compliance.createChecklist('Q1 SOX', 'sox-quarterly');
    expect(result.id).toBeTruthy();
    expect(result.items).toBe(5);
    checklistId = result.id;
  });

  it('gets status', () => {
    const status = compliance.getStatus(checklistId);
    expect(status.items).toHaveLength(5);
    expect(status.progress).toBe(0);
    itemId = status.items[0].id;
  });

  it('updates item', () => {
    const item = compliance.updateItem(itemId, { status: 'completed', assignee: 'alice' });
    expect((item as any).status).toBe('completed');
  });

  it('generates report', () => {
    const report = compliance.generateReport(checklistId);
    expect(report.completed).toBe(1);
    expect(report.progress).toBe('20%');
  });
});

describe('deal flow', () => {
  let dealId: string;

  it('adds deal', () => {
    const deal = dealflow.addDeal('Acme Contract', { company: 'Acme', value: 50000 });
    expect(deal.id).toBeTruthy();
    dealId = deal.id;
  });

  it('updates stage', () => {
    const deal = dealflow.updateStage(dealId, 'proposal') as any;
    expect(deal.stage).toBe('proposal');
  });

  it('gets pipeline', () => {
    const pipeline = dealflow.getPipeline();
    expect(pipeline.count).toBeGreaterThanOrEqual(1);
    expect(pipeline.total_value).toBe(50000);
  });

  it('adds note', () => {
    const note = dealflow.addNote(dealId, 'Great meeting', 'bob');
    expect(note.content).toBe('Great meeting');
  });
});

describe('support', () => {
  let ticketId: string;

  it('creates ticket', () => {
    const ticket = support.createTicket('Login broken', { priority: 'high', customer: 'jane' });
    expect(ticket.id).toBeTruthy();
    ticketId = ticket.id;
  });

  it('escalates', () => {
    const result = support.escalate(ticketId);
    expect(result.escalation_level).toBe(1);
  });

  it('gets queue', () => {
    const queue = support.getQueue({ status: 'escalated' });
    expect((queue as any[]).length).toBeGreaterThanOrEqual(1);
  });

  it('resolves', () => {
    const ticket = support.resolve(ticketId, 'Fixed auth service') as any;
    expect(ticket.status).toBe('resolved');
  });
});
