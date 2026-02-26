// PM2 Ecosystem Config for GetContact AI Agent
// Install PM2: npm install -g pm2
// Run: pm2 start ecosystem.config.cjs
// Stop: pm2 stop all
// Restart: pm2 restart all
// Logs: pm2 logs

module.exports = {
  apps: [
    {
      name: 'whatsapp-service',
      script: 'node_modules/.bin/ts-node',
      args: 'src/index.ts',
      cwd: 'F:\\Programming\\GetContactAIAgent\\whatsapp-service',
      watch: false,
      autorestart: true,
      max_restarts: 10,
      min_uptime: '10s',
      env: {
        NODE_ENV: 'production',
      },
    },
    {
      name: 'orchestrator',
      script: 'python',
      args: '-m uvicorn orchestrator.main:app --port 8000 --host 0.0.0.0',
      cwd: 'F:\\Programming\\GetContactAIAgent',
      interpreter: 'python',
      watch: false,
      autorestart: true,
      max_restarts: 10,
      min_uptime: '10s',
    },
    {
      name: 'frontend',
      script: 'npm',
      args: 'run dev',
      cwd: 'F:\\Programming\\GetContactAIAgent\\frontend',
      watch: false,
      autorestart: true,
      max_restarts: 10,
      min_uptime: '10s',
      env: {
        NODE_ENV: 'development',
      },
    },
  ],
};
