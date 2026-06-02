// scripts/merge_epg.js
const fs = require('fs');
const path = require('path');
const zlib = require('zlib');
const { XMLParser, XMLBuilder } = require('fast-xml-parser');

const WORKSPACE = process.env.GITHUB_WORKSPACE || __dirname + '/..';

// 配置
const CONFIG = {
  M3U_PATH: path.join(WORKSPACE, 'playlist', 'Ofiii.m3u'),
  OUTPUT_DIR: path.join(WORKSPACE, 'output'),
  OUTPUT_FILE: '4gtv_tv.xml.gz',
  EPG_4G_URL: 'https://raw.githubusercontent.com/myhomebox/EPG/refs/heads/main/output/4g.xml',
  EPG_OFIII_URL: 'https://raw.githubusercontent.com/myhomebox/EPG/refs/heads/main/output/ofiii.xml',
};

// 解析 M3U 提取 tvg-name 列表
function parseM3U(m3uContent) {
  const names = new Set();
  const lines = m3uContent.split('\n');
  for (const line of lines) {
    const match = line.match(/tvg-name="([^"]+)"/);
    if (match) {
      names.add(match[1]);
    }
  }
  return names;
}

// 从 ofiii XML 中提取指定频道的 channel + programme 节点（字符串形式）
function extractChannelData(xmlText, targetNames) {
  // 匹配一个完整的 <channel ...> ... </channel> 块
  const channelRegex = /<channel\b[^>]*>[\s\S]*?<\/channel>/g;
  const programmeRegex = /<programme\b[^>]*>[\s\S]*?<\/programme>/g;

  let channels = [];
  let programmes = [];

  // 提取所有 channel
  let chMatch;
  while ((chMatch = channelRegex.exec(xmlText)) !== null) {
    // 提取 id 属性
    const idMatch = chMatch[0].match(/id="([^"]+)"/);
    if (idMatch && targetNames.has(idMatch[1])) {
      channels.push(chMatch[0]);
    }
  }

  // 提取所有 programme，按 channel 属性过滤
  let progMatch;
  while ((progMatch = programmeRegex.exec(xmlText)) !== null) {
    const chAttr = progMatch[0].match(/channel="([^"]+)"/);
    if (chAttr && targetNames.has(chAttr[1])) {
      programmes.push(progMatch[0]);
    }
  }

  return { channels, programmes };
}

// 将提取的内容插入到 4g.xml 的 </tv> 之前
function mergeXML(baseXML, channels, programmes) {
  // 简单方法：找到 </tv> 并在此之前插入
  const insertPoint = baseXML.lastIndexOf('</tv>');
  if (insertPoint === -1) throw new Error('Invalid 4g.xml: missing </tv>');

  const insertion = '\n' + channels.join('\n') + '\n' + programmes.join('\n') + '\n';
  const merged = baseXML.slice(0, insertPoint) + insertion + baseXML.slice(insertPoint);
  return merged;
}

async function main() {
  try {
    // 1. 读取 M3U
    console.log('Reading M3U...');
    const m3uContent = fs.readFileSync(CONFIG.M3U_PATH, 'utf-8');
    const targetNames = parseM3U(m3uContent);
    console.log(`Found ${targetNames.size} channels in M3U:`, [...targetNames]);

    if (targetNames.size === 0) {
      console.log('No channels found, exiting.');
      return;
    }

    // 2. 下载两个 EPG 文件
    console.log('Fetching 4g.xml...');
    const resp4g = await fetch(CONFIG.EPG_4G_URL);
    const xml4g = await resp4g.text();

    console.log('Fetching ofiii.xml...');
    const respOfiii = await fetch(CONFIG.EPG_OFIII_URL);
    const xmlOfiii = await respOfiii.text();

    // 3. 从 ofiii.xml 中提取需要的频道
    const { channels, programmes } = extractChannelData(xmlOfiii, targetNames);
    console.log(`Extracted ${channels.length} channels and ${programmes.length} programmes.`);

    // 4. 合并 XML
    const mergedXML = mergeXML(xml4g, channels, programmes);

    // 5. 写入压缩文件
    if (!fs.existsSync(CONFIG.OUTPUT_DIR)) {
      fs.mkdirSync(CONFIG.OUTPUT_DIR, { recursive: true });
    }
    const outputPath = path.join(CONFIG.OUTPUT_DIR, CONFIG.OUTPUT_FILE);
    const gzipStream = zlib.createGzip({ level: 9 });
    const outStream = fs.createWriteStream(outputPath);
    gzipStream.pipe(outStream);
    gzipStream.write(mergedXML);
    gzipStream.end();

    await new Promise((resolve, reject) => {
      outStream.on('finish', resolve);
      outStream.on('error', reject);
    });

    console.log(`Successfully created ${outputPath}`);
  } catch (err) {
    console.error('Error:', err);
    process.exit(1);
  }
}

main();
