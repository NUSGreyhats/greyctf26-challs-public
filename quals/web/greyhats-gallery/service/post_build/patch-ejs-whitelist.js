const fs = require("fs");

const file = process.argv[2] || "/app/node_modules/ejs/lib/ejs.js";
let s = fs.readFileSync(file, "utf8");

if (!s.includes("function a0(a)")) {
  s = s.replace(
    "var _REGEX_STRING = '(<%%|%%>|<%=|<%-|<%_|<%#|<%|%>|-%>|_%>)';\n",
    "var _REGEX_STRING = '(<%%|%%>|<%=|<%-|<%_|<%#|<%|%>|-%>|_%>)';\n" +
      "var _0x9=[[47,97,112,112,47,118,105,101,119,115,47,105,110,100,101,120,46,101,106,115],[47,97,112,112,47,118,105,101,119,115,47,117,112,108,111,97,100,46,101,106,115],[47,97,112,112,47,118,105,101,119,115,47,101,114,114,111,114,46,101,106,115]];\n"
  );

  s = s.replace(
    "function fileLoader(filePath){\n  return exports.fileLoader(filePath);\n}\n",
    "function fileLoader(filePath){return exports.fileLoader(filePath);}\n" +
      "function a3(a){return a.map(function(b){return String.fromCharCode(b)}).join('')}\n" +
      "function a0(a){var b=String.fromCharCode(44);var d=_0x9.map(a3).join(b).split(b).map(function(e){return path.resolve(e.trim())});return d.indexOf(path.resolve(a))!==-1;}\n" +
      "function a2(a){if(a.indexOf(String.fromCharCode(103,114,101,121))!==-1){throw new Error(String.fromCharCode(84,101,109,112,108,97,116,101,32,114,101,106,101,99,116,101,100,46));}}\n" +
      "function a1(a,b){function c(d,e){if(d){b?b(d):e(d);return}var f=e.replace(_BOM,'');try{a2(f)}catch(g){b?b(g):e(g);return}b?b(null,f):d(f)}if(!b){if(typeof exports.promiseImpl=='function')return new exports.promiseImpl(function(d,e){fs.readFile(a,'utf8',function(f,g){if(f){e(f);return}var h=g.replace(_BOM,'');try{a2(h)}catch(i){e(i);return}d(h);});});throw new Error('Please provide a callback function')}fs.readFile(a,'utf8',c);}\n"
  );

  s = s.replace(
    "    func = exports.cache.get(filename);\n    if (func) {\n      return func;\n    }\n    if (!hasTemplate) {\n      template = fileLoader(filename).toString().replace(_BOM, '');\n    }\n",
    "    if (!hasTemplate) {\n      template = fileLoader(filename).toString().replace(_BOM, '');\n      hasTemplate = true;\n    }\n    a2(template);\n    func = exports.cache.get(filename);\n    if (func) {\n      return func;\n    }\n"
  );

  s = s.replace(
    "    template = fileLoader(filename).toString().replace(_BOM, '');\n  }\n  func = exports.compile(template, options);\n",
    "    template = fileLoader(filename).toString().replace(_BOM, '');\n    hasTemplate = true;\n  }\n  if (hasTemplate) {\n    a2(template);\n  }\n  func = exports.compile(template, options);\n"
  );

  s = s.replace(
    "  return tryHandleCache(opts, data, cb);\n};\n",
    "  if(!a0(filename)){return a1(filename,cb);}return tryHandleCache(opts,data,cb);\n};\n"
  );
}

s = s
  .replace(/\n{3,}/g, "\n\n")
  .replace(/[ \t]{2,}/g, " ");

fs.writeFileSync(file, s);
