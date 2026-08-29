// PM2 ecosystem — Adfix
// Kurulum: pm2 start ecosystem.config.js
//          pm2 save && pm2 startup
module.exports = {
  apps: [{
    name: "adfix",
    cwd: "/home/sagunmed/SagunMedBeta/Adfix/backend",
    script: "main.py",
    interpreter: "python3",
    env: {
      ADFIX_PORT: "8002",
      ADFIX_JWT_SECRET: "__BURAYA_GUCLU_ANAHTAR__",
      ADFIX_SUPER_SIFRE: "__MERKEZ_YONETICI_SIFRESI__"
    },
    max_restarts: 10,
    restart_delay: 3000,
    watch: false,
    log_date_format: "YYYY-MM-DD HH:mm:ss",
    error_file: "/home/sagunmed/logs/adfix-err.log",
    out_file: "/home/sagunmed/logs/adfix-out.log",
    merge_logs: true
  }]
};
