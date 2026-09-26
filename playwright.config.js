const {defineConfig} = require('@playwright/test');
module.exports = defineConfig({
  testDir:'./tests/ui', timeout:30000, workers:1,
  use:{browserName:'chromium', channel:'msedge', viewport:{width:1280,height:860}, headless:true},
});
