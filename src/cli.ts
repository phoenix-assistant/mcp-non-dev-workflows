#!/usr/bin/env node
import { Command } from 'commander';
import { createServer } from './server.js';
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js';
import { getDb } from './storage.js';
import { templates } from './workflows/compliance.js';

const program = new Command()
  .name('mcp-workflows')
  .description('MCP server for non-dev workflows: compliance, deal flow, support')
  .version('0.1.0');

program.command('serve')
  .description('Start the MCP server (stdio transport)')
  .option('--db <path>', 'Database directory path')
  .action(async (opts) => {
    if (opts.db) getDb(opts.db);
    else getDb();
    const server = createServer();
    const transport = new StdioServerTransport();
    await server.connect(transport);
  });

program.command('init')
  .description('Initialize workflow templates')
  .argument('<type>', 'Workflow type: compliance, deals, or support')
  .action((type) => {
    getDb();
    if (type === 'compliance') {
      console.log('Available compliance templates:');
      templates.forEach(t => console.log(`  - ${t}`));
      console.log('\nUse compliance_create_checklist with a template name to get started.');
    } else if (type === 'deals') {
      console.log('Deal pipeline initialized with stages:');
      console.log('  prospecting → qualification → proposal → negotiation → closed_won/closed_lost');
    } else if (type === 'support') {
      console.log('Support queue initialized.');
      console.log('  Priorities: low, medium, high, critical');
      console.log('  Escalation levels auto-increment on escalate.');
    } else {
      console.error(`Unknown type: ${type}. Use: compliance, deals, or support`);
      process.exit(1);
    }
    console.log('\nDatabase ready. Run `mcp-workflows serve` to start the MCP server.');
  });

program.parse();
