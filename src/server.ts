import { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import { z } from 'zod';
import * as compliance from './workflows/compliance.js';
import * as dealflow from './workflows/dealflow.js';
import * as support from './workflows/support.js';

export function createServer() {
  const server = new McpServer({ name: 'mcp-non-dev-workflows', version: '0.1.0' });

  // === Compliance ===
  server.tool('compliance_create_checklist', 'Create a compliance checklist, optionally from a template',
    { name: z.string(), template: z.string().optional() },
    async ({ name, template }) => ({ content: [{ type: 'text', text: JSON.stringify(compliance.createChecklist(name, template), null, 2) }] })
  );
  server.tool('compliance_update_item', 'Update a compliance checklist item',
    { item_id: z.string(), status: z.enum(['pending', 'in_progress', 'completed', 'failed']).optional(), assignee: z.string().optional(), notes: z.string().optional() },
    async ({ item_id, ...rest }) => ({ content: [{ type: 'text', text: JSON.stringify(compliance.updateItem(item_id, rest), null, 2) }] })
  );
  server.tool('compliance_get_status', 'Get checklist status and progress',
    { checklist_id: z.string() },
    async ({ checklist_id }) => ({ content: [{ type: 'text', text: JSON.stringify(compliance.getStatus(checklist_id), null, 2) }] })
  );
  server.tool('compliance_generate_report', 'Generate a compliance report',
    { checklist_id: z.string() },
    async ({ checklist_id }) => ({ content: [{ type: 'text', text: JSON.stringify(compliance.generateReport(checklist_id), null, 2) }] })
  );

  // === Deal Flow ===
  server.tool('deal_flow_add_deal', 'Add a new deal to the pipeline',
    { name: z.string(), company: z.string().optional(), value: z.number().optional(), owner: z.string().optional(), stage: z.string().optional() },
    async ({ name, ...opts }) => ({ content: [{ type: 'text', text: JSON.stringify(dealflow.addDeal(name, opts), null, 2) }] })
  );
  server.tool('deal_flow_update_stage', 'Update deal stage',
    { deal_id: z.string(), stage: z.string() },
    async ({ deal_id, stage }) => ({ content: [{ type: 'text', text: JSON.stringify(dealflow.updateStage(deal_id, stage), null, 2) }] })
  );
  server.tool('deal_flow_get_pipeline', 'Get deal pipeline overview',
    { stage: z.string().optional(), owner: z.string().optional() },
    async (filters) => ({ content: [{ type: 'text', text: JSON.stringify(dealflow.getPipeline(filters), null, 2) }] })
  );
  server.tool('deal_flow_add_note', 'Add a note to a deal',
    { deal_id: z.string(), content: z.string(), author: z.string().optional() },
    async ({ deal_id, content, author }) => ({ content: [{ type: 'text', text: JSON.stringify(dealflow.addNote(deal_id, content, author), null, 2) }] })
  );

  // === Support ===
  server.tool('support_create_ticket', 'Create a support ticket',
    { title: z.string(), description: z.string().optional(), priority: z.enum(['low', 'medium', 'high', 'critical']).optional(), customer: z.string().optional(), assignee: z.string().optional() },
    async ({ title, ...opts }) => ({ content: [{ type: 'text', text: JSON.stringify(support.createTicket(title, opts), null, 2) }] })
  );
  server.tool('support_escalate', 'Escalate a support ticket',
    { ticket_id: z.string(), reason: z.string().optional() },
    async ({ ticket_id, reason }) => ({ content: [{ type: 'text', text: JSON.stringify(support.escalate(ticket_id, reason), null, 2) }] })
  );
  server.tool('support_get_queue', 'Get support ticket queue',
    { status: z.string().optional(), priority: z.string().optional(), assignee: z.string().optional() },
    async (filters) => ({ content: [{ type: 'text', text: JSON.stringify(support.getQueue(filters), null, 2) }] })
  );
  server.tool('support_resolve', 'Resolve a support ticket',
    { ticket_id: z.string(), resolution: z.string().optional() },
    async ({ ticket_id, resolution }) => ({ content: [{ type: 'text', text: JSON.stringify(support.resolve(ticket_id, resolution), null, 2) }] })
  );

  return server;
}
