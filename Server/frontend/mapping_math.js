(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  if (root) root.MappingMath = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';

  const EPS = 1e-12;

  function finite(value, message = '表达式无法计算') {
    const number = Number(value);
    if (!Number.isFinite(number)) throw new Error(message);
    return number;
  }

  function escapeRegExp(text) {
    return String(text).replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  }

  function substituteVariables(expression, values) {
    let text = String(expression ?? '').trim();
    const entries = Object.entries(values || {})
      .map(([name, value]) => [String(name), Number(value)])
      .filter(([name, value]) => name && Number.isFinite(value))
      .sort((a, b) => b[0].length - a[0].length);

    for (const [name, value] of entries) {
      // Match the server evaluator's token-boundary semantics so a variable
      // named "a" cannot rewrite the "a" inside tan(...).
      const escaped = escapeRegExp(name);
      const pattern = new RegExp(`(^|[^\\p{L}\\p{N}_/])${escaped}(?=$|[^\\p{L}\\p{N}_/])`, 'gu');
      text = text.replace(pattern, (_match, prefix) => `${prefix}(${value})`);
    }
    return text;
  }

  function makeParser(expression) {
    const text = String(expression ?? '').trim();
    let index = 0;

    const skip = () => { while (/\s/.test(text[index] || '')) index += 1; };
    const peek = value => text.slice(index, index + value.length) === value;
    const consume = value => {
      skip();
      if (!peek(value)) return false;
      index += value.length;
      return true;
    };
    const error = message => { throw new Error(`${message}（位置 ${index + 1}）`); };

    function parseNumber() {
      skip();
      const match = text.slice(index).match(/^(?:\d+(?:\.\d*)?|\.\d+)(?:e[+-]?\d+)?/i);
      if (!match) return null;
      index += match[0].length;
      return finite(match[0]);
    }

    function parseIdentifier() {
      skip();
      const match = text.slice(index).match(/^[A-Za-z_][A-Za-z0-9_]*/);
      if (!match) return '';
      index += match[0].length;
      return match[0];
    }

    function callFunction(name, args) {
      const functions = {
        abs: xs => Math.abs(xs[0]),
        min: xs => Math.min(...xs),
        max: xs => Math.max(...xs),
        round: xs => {
          const digits = xs.length > 1 ? Math.trunc(xs[1]) : 0;
          const factor = 10 ** digits;
          return Math.round((xs[0] + Number.EPSILON) * factor) / factor;
        },
        sqrt: xs => Math.sqrt(xs[0]),
        sin: xs => Math.sin(xs[0]),
        cos: xs => Math.cos(xs[0]),
        tan: xs => Math.tan(xs[0]),
        radians: xs => xs[0] * Math.PI / 180,
        degrees: xs => xs[0] * 180 / Math.PI,
      };
      if (!Object.prototype.hasOwnProperty.call(functions, name)) error(`不支持的函数 ${name}`);
      return finite(functions[name](args));
    }

    function atom() {
      skip();
      if (consume('(')) {
        const value = sum();
        if (!consume(')')) error('缺少右括号');
        return value;
      }

      const number = parseNumber();
      if (number !== null) return number;

      const name = parseIdentifier();
      if (!name) error('仅支持数值、已解析变量、幂运算和白名单数学函数');
      if (name === 'pi') return Math.PI;
      if (name === 'e') return Math.E;
      if (!consume('(')) error(`未知变量 ${name}`);
      const args = [];
      skip();
      if (!consume(')')) {
        for (;;) {
          args.push(sum());
          if (consume(')')) break;
          if (!consume(',')) error('函数参数缺少逗号或右括号');
        }
      }
      return callFunction(name, args);
    }

    // Python-compatible precedence: exponentiation binds tighter than unary
    // minus, and the exponent accepts a unary expression (2**-2 is valid).
    function power() {
      const left = atom();
      skip();
      if (consume('**')) return finite(Math.pow(left, factor()));
      return left;
    }

    function factor() {
      skip();
      if (consume('+')) return factor();
      if (consume('-')) return -factor();
      return power();
    }

    function product() {
      let value = factor();
      for (;;) {
        skip();
        if (peek('**')) break;
        if (consume('*')) value = finite(value * factor());
        else if (consume('/')) value = finite(value / factor());
        else if (consume('%')) value = finite(value % factor());
        else break;
      }
      return value;
    }

    function sum() {
      let value = product();
      for (;;) {
        if (consume('+')) value = finite(value + product());
        else if (consume('-')) value = finite(value - product());
        else break;
      }
      return value;
    }

    return {
      parse() {
        if (!text) throw new Error('表达式为空');
        const value = sum();
        skip();
        if (index !== text.length) error('存在无法解析的内容');
        return finite(value);
      },
    };
  }

  function evaluateExpression(expression, values = {}) {
    return makeParser(substituteVariables(expression, values)).parse();
  }

  function normalizeRows(rows) {
    const dedup = new Map();
    for (const item of rows || []) {
      if (!item || item.length < 2) continue;
      const source = Number(item[0]), target = Number(item[1]);
      if (!Number.isFinite(source) || !Number.isFinite(target)) continue;
      const key = Math.round(source * 1e9) / 1e9;
      // Legacy V21 behavior: when the same source coordinate occurs more than
      // once, the last imported row wins.
      dedup.set(key, [source, target]);
    }
    const result = [...dedup.values()].sort((a, b) => a[0] - b[0]);
    if (result.length && (result[0][0] > EPS || result[result.length - 1][0] < -EPS)) {
      result.push([0, 0]);
      result.sort((a, b) => a[0] - b[0]);
    }
    return result;
  }

  const MAPPING_INTERPOLATION_MODE = 'minimum_jerk_quintic';
  const curveCache = new WeakMap();

  function curveFingerprint(rawRows) {
    if (!Array.isArray(rawRows)) return 'not-array';
    let sx = 0, sy = 0, mix = 0;
    for (let i = 0; i < rawRows.length; i += 1) {
      const row = rawRows[i];
      const x = Number(row?.[0]), y = Number(row?.[1]);
      if (!Number.isFinite(x) || !Number.isFinite(y)) continue;
      const weight = i + 1;
      sx += x * weight;
      sy += y * weight;
      mix += (x * 0.6180339887498949 + y * 1.4142135623730951) * ((weight % 97) + 1);
    }
    return `${rawRows.length}|${sx}|${sy}|${mix}`;
  }

  function matAdd(a, b) {
    return [a[0] + b[0], a[1] + b[1], a[2] + b[2], a[3] + b[3]];
  }
  function matSub(a, b) {
    return [a[0] - b[0], a[1] - b[1], a[2] - b[2], a[3] - b[3]];
  }
  function matMul(a, b) {
    return [
      a[0] * b[0] + a[1] * b[2], a[0] * b[1] + a[1] * b[3],
      a[2] * b[0] + a[3] * b[2], a[2] * b[1] + a[3] * b[3],
    ];
  }
  function matVec(a, value) {
    return [a[0] * value[0] + a[1] * value[1], a[2] * value[0] + a[3] * value[1]];
  }
  function vecSub(a, b) { return [a[0] - b[0], a[1] - b[1]]; }
  function transpose(a) { return [a[0], a[2], a[1], a[3]]; }

  function inverse2(a) {
    let a00 = a[0], a01 = a[1], a10 = a[2], a11 = a[3];
    let determinant = a00 * a11 - a01 * a10;
    const scale = Math.max(Math.abs(a00 * a11), Math.abs(a01 * a10), 1);
    if (Math.abs(determinant) <= 1e-15 * scale) {
      const regularizer = Math.max(Math.abs(a00), Math.abs(a11), 1) * 1e-12;
      a00 += regularizer; a11 += regularizer;
      determinant = a00 * a11 - a01 * a10;
    }
    if (!Number.isFinite(determinant) || Math.abs(determinant) <= 1e-300) {
      throw new Error('映射最小 jerk 求解器数值奇异');
    }
    const inverse = 1 / determinant;
    return [a11 * inverse, -a01 * inverse, -a10 * inverse, a00 * inverse];
  }

  function segmentSystem(step, delta) {
    const h = Math.max(Number(step), 1e-15);
    const h2 = h * h, h3 = h2 * h, h4 = h3 * h;
    return {
      h00: [384 / h3, 72 / h2, 72 / h2, 18 / h],
      h01: [336 / h3, -48 / h2, 48 / h2, -6 / h],
      h11: [384 / h3, -72 / h2, -72 / h2, 18 / h],
      rhs0: [720 * delta / h4, 120 * delta / h3],
      rhs1: [720 * delta / h4, -120 * delta / h3],
    };
  }

  function blockSolve(diagonal, upper, rhs) {
    const count = diagonal.length;
    if (!count) return [];
    if (count === 1) return [matVec(inverse2(diagonal[0]), rhs[0])];
    const cPrime = Array.from({length:count - 1}, () => [0, 0, 0, 0]);
    const dPrime = Array.from({length:count}, () => [0, 0]);
    let inverse = inverse2(diagonal[0]);
    cPrime[0] = matMul(inverse, upper[0]);
    dPrime[0] = matVec(inverse, rhs[0]);
    for (let i = 1; i < count; i += 1) {
      const lower = transpose(upper[i - 1]);
      const effective = matSub(diagonal[i], matMul(lower, cPrime[i - 1]));
      const effectiveRhs = vecSub(rhs[i], matVec(lower, dPrime[i - 1]));
      inverse = inverse2(effective);
      if (i < count - 1) cPrime[i] = matMul(inverse, upper[i]);
      dPrime[i] = matVec(inverse, effectiveRhs);
    }
    const solution = Array.from({length:count}, () => [0, 0]);
    solution[count - 1] = dPrime[count - 1];
    for (let i = count - 2; i >= 0; i -= 1) {
      solution[i] = vecSub(dPrime[i], matVec(cPrime[i], solution[i + 1]));
    }
    return solution;
  }

  function segmentCoefficients(y0, y1, step, left, right) {
    const h = Number(step), delta = Number(y1) - Number(y0);
    const d0 = h * left[0], d1 = h * right[0];
    const dd0 = h * h * left[1], dd1 = h * h * right[1];
    return [
      Number(y0), d0, 0.5 * dd0,
      10 * delta - 6 * d0 - 4 * d1 - 1.5 * dd0 + 0.5 * dd1,
      -15 * delta + 8 * d0 + 7 * d1 + 1.5 * dd0 - dd1,
      6 * delta - 3 * d0 - 3 * d1 - 0.5 * dd0 + 0.5 * dd1,
    ];
  }

  function linearCoefficients(y0, y1) { return [Number(y0), Number(y1) - Number(y0), 0, 0, 0, 0]; }

  function compileMinimumJerkCurve(rawRows) {
    const canCache = rawRows && typeof rawRows === 'object';
    const fingerprint = canCache ? curveFingerprint(rawRows) : '';
    if (canCache) {
      const cached = curveCache.get(rawRows);
      if (cached && cached.fingerprint === fingerprint) return cached.curve;
    }

    const rows = normalizeRows(rawRows);
    const count = rows.length;
    let coefficients = [];
    if (count === 2) {
      coefficients = [linearCoefficients(rows[0][1], rows[1][1])];
    } else if (count >= 3) {
      const start = rows[0][0], span = rows[count - 1][0] - start;
      if (!(span > EPS)) throw new Error('映射源坐标范围无效');
      const parameters = rows.map(row => (row[0] - start) / span);
      const diagonal = Array.from({length:count}, () => [0, 0, 0, 0]);
      const upper = Array.from({length:count - 1}, () => [0, 0, 0, 0]);
      const rhs = Array.from({length:count}, () => [0, 0]);
      for (let i = 0; i < count - 1; i += 1) {
        const step = parameters[i + 1] - parameters[i];
        if (!(step > 1e-15)) throw new Error('映射源坐标必须严格递增');
        const system = segmentSystem(step, rows[i + 1][1] - rows[i][1]);
        diagonal[i] = matAdd(diagonal[i], system.h00);
        upper[i] = matAdd(upper[i], system.h01);
        diagonal[i + 1] = matAdd(diagonal[i + 1], system.h11);
        rhs[i] = [rhs[i][0] + system.rhs0[0], rhs[i][1] + system.rhs0[1]];
        rhs[i + 1] = [rhs[i + 1][0] + system.rhs1[0], rhs[i + 1][1] + system.rhs1[1]];
      }
      const derivatives = blockSolve(diagonal, upper, rhs);
      coefficients = Array.from({length:count - 1}, (_, i) => segmentCoefficients(
        rows[i][1], rows[i + 1][1], parameters[i + 1] - parameters[i], derivatives[i], derivatives[i + 1],
      ));
    }
    const curve = {rows, coefficients, mode:MAPPING_INTERPOLATION_MODE};
    if (canCache) curveCache.set(rawRows, {fingerprint, curve});
    return curve;
  }

  function runtimeRows(rawRows) { return compileMinimumJerkCurve(rawRows).rows; }

  function segmentIndex(rows, source) {
    let lo = 0, hi = rows.length - 1;
    while (hi - lo > 1) {
      const mid = Math.floor((lo + hi) / 2);
      if (rows[mid][0] <= source) lo = mid; else hi = mid;
    }
    return Math.max(0, Math.min(lo, rows.length - 2));
  }

  function evalPolynomial(coefficients, u, derivative = 0) {
    const [c0, c1, c2, c3, c4, c5] = coefficients;
    if (derivative <= 0) return (((((c5 * u + c4) * u + c3) * u + c2) * u + c1) * u + c0);
    if (derivative === 1) return ((((5 * c5 * u + 4 * c4) * u + 3 * c3) * u + 2 * c2) * u + c1);
    if (derivative === 2) return (((20 * c5 * u + 12 * c4) * u + 6 * c3) * u + 2 * c2);
    if (derivative === 3) return ((60 * c5 * u + 24 * c4) * u + 6 * c3);
    if (derivative === 4) return 120 * c5 * u + 24 * c4;
    return 120 * c5;
  }

  function mappingNumber(value) {
    const number = finite(value);
    if (Math.abs(number) < 0.005) return '0';
    return Number(number.toFixed(2)).toString();
  }

  function mapPosition(rawRows, sourceValue) {
    const curve = compileMinimumJerkCurve(rawRows);
    const rows = curve.rows;
    if (!rows.length) throw new Error('伴生驱动尚未导入有效映射 CSV');
    const source = finite(sourceValue);
    if (rows.length === 1 || source <= rows[0][0]) return rows[0][1];
    if (source >= rows[rows.length - 1][0]) return rows[rows.length - 1][1];
    const index = segmentIndex(rows, source);
    const width = Math.max(rows[index + 1][0] - rows[index][0], EPS);
    const u = Math.max(0, Math.min(1, (source - rows[index][0]) / width));
    return evalPolynomial(curve.coefficients[index], u);
  }

  function mapDerivatives(rawRows, sourceValue) {
    const curve = compileMinimumJerkCurve(rawRows);
    const rows = curve.rows;
    if (!rows.length) throw new Error('伴生驱动尚未导入有效映射 CSV');
    if (rows.length === 1) return [rows[0][1], 0, 0, 0];
    const source = Math.max(rows[0][0], Math.min(rows[rows.length - 1][0], finite(sourceValue)));
    const index = segmentIndex(rows, source);
    const width = Math.max(rows[index + 1][0] - rows[index][0], EPS);
    const u = Math.max(0, Math.min(1, (source - rows[index][0]) / width));
    const coeff = curve.coefficients[index];
    return [
      evalPolynomial(coeff, u, 0),
      evalPolynomial(coeff, u, 1) / width,
      evalPolynomial(coeff, u, 2) / (width * width),
      evalPolynomial(coeff, u, 3) / (width * width * width),
    ];
  }

  function inverseMapPosition(rawRows, targetValue, preferredSource = 0) {
    const curve = compileMinimumJerkCurve(rawRows);
    const rows = curve.rows;
    if (!rows.length) throw new Error('伴生驱动尚未导入有效映射 CSV');
    const target = finite(targetValue), preferred = finite(preferredSource);
    if (rows.length === 1) return rows[0][0];

    const exact = rows
      .filter(([, value]) => Math.abs(value - target) <= 1e-9)
      .map(([source]) => [Math.abs(source - preferred), source])
      .sort((a, b) => a[0] - b[0] || a[1] - b[1]);
    if (exact.length) return exact[0][1];

    const candidates = [];
    for (let i = 0; i < rows.length - 1; i += 1) {
      const [x0, y0] = rows[i], [x1, y1] = rows[i + 1];
      let f0 = y0 - target, f1 = y1 - target;
      if (f0 === 0) { candidates.push([Math.abs(x0 - preferred), x0]); continue; }
      if (f1 === 0) { candidates.push([Math.abs(x1 - preferred), x1]); continue; }
      if (f0 * f1 > 0) continue;
      let leftU = 0, rightU = 1, leftF = f0;
      for (let iteration = 0; iteration < 42; iteration += 1) {
        const midU = 0.5 * (leftU + rightU);
        const midF = evalPolynomial(curve.coefficients[i], midU) - target;
        if (Math.abs(midF) <= 1e-11) { leftU = midU; rightU = midU; break; }
        if (leftF * midF <= 0) rightU = midU;
        else { leftU = midU; leftF = midF; }
      }
      const u = 0.5 * (leftU + rightU);
      const source = x0 + u * (x1 - x0);
      candidates.push([Math.abs(source - preferred), source]);
    }
    if (candidates.length) {
      candidates.sort((a, b) => a[0] - b[0] || a[1] - b[1]);
      return candidates[0][1];
    }
    const fallback = rows
      .map(([source, value]) => [Math.abs(value - target), Math.abs(source - preferred), source])
      .sort((a, b) => a[0] - b[0] || a[1] - b[1] || a[2] - b[2]);
    return fallback.length ? fallback[0][2] : preferred;
  }

  function stripWholeOuterParens(expression) {
    let text = String(expression ?? '').trim();
    for (;;) {
      if (!(text.startsWith('(') && text.endsWith(')'))) return text;
      let depth = 0;
      let closesAtEnd = false;
      for (let i = 0; i < text.length; i += 1) {
        if (text[i] === '(') depth += 1;
        else if (text[i] === ')') {
          depth -= 1;
          if (depth === 0) {
            closesAtEnd = i === text.length - 1;
            break;
          }
          if (depth < 0) return text;
        }
      }
      if (!closesAtEnd) return text;
      text = text.slice(1, -1).trim();
    }
  }

  function topLevelDifference(expression) {
    const text = stripWholeOuterParens(expression);
    let depth = 0;
    let lastAdditive = null;

    const previousNonSpace = position => {
      for (let j = position - 1; j >= 0; j -= 1) if (!/\s/.test(text[j])) return text[j];
      return '';
    };

    for (let i = 0; i < text.length; i += 1) {
      const ch = text[i];
      if (ch === '(') { depth += 1; continue; }
      if (ch === ')') { depth -= 1; continue; }
      if (depth !== 0 || (ch !== '+' && ch !== '-')) continue;

      const prev = previousNonSpace(i);
      const next = text.slice(i + 1).match(/\S/)?.[0] || '';
      const exponentSign = /[eE]/.test(prev) && /\d/.test(next);
      const unary = !prev || '+-*/%(,'.includes(prev) || exponentSign;
      if (!unary) lastAdditive = {index: i, operator: ch};
    }

    if (!lastAdditive || lastAdditive.operator !== '-') return null;
    return [text.slice(0, lastAdditive.index), text.slice(lastAdditive.index + 1)];
  }

  function mappedTravelExpression(rawRows, startValue, expression, inverse = false, values = {}) {
    const rows = normalizeRows(rawRows);
    const start = finite(startValue);
    const raw = String(expression ?? '').trim();
    const travel = evaluateExpression(raw, values);
    const parts = topLevelDifference(raw);

    // Exactly mirror the later V21 rule: only a root-level subtraction is an
    // explicit absolute endpoint pair. Polynomial sub-expressions containing
    // "-" are not accidentally reclassified.
    if (parts) {
      const endValue = evaluateExpression(parts[0], values);
      const explicitStart = evaluateExpression(parts[1], values);
      const left = inverse
        ? inverseMapPosition(rows, endValue, start)
        : mapPosition(rows, endValue);
      const right = inverse
        ? inverseMapPosition(rows, explicitStart, start)
        : mapPosition(rows, explicitStart);
      return `${mappingNumber(left)}-${mappingNumber(right)}`;
    }

    if (inverse) {
      const companionStart = mapPosition(rows, start);
      const sourceEnd = inverseMapPosition(rows, companionStart + travel, start);
      return mappingNumber(sourceEnd - start);
    }
    return mappingNumber(mapPosition(rows, start + travel) - mapPosition(rows, start));
  }

  function sourceSegmentStart({schedule = [], drive, segment, segmentIndex = 0, relation = null, variables = {}}) {
    const scheduled = (schedule || []).find(item =>
      item && item.id === segment?.id && (!drive?.id || !item.drive_id || item.drive_id === drive.id)
    );
    const sourceRef = String(relation?.segment?.mapping_source_joint_id || '');
    if (scheduled) {
      if (sourceRef === `drive:${drive?.id}` && Number.isFinite(Number(scheduled.drive_position_start))) {
        return Number(scheduled.drive_position_start);
      }
      if (drive?.joint_id && sourceRef === drive.joint_id && Number.isFinite(Number(scheduled.joint_position_start))) {
        return Number(scheduled.joint_position_start);
      }
      if (Number.isFinite(Number(scheduled.travel_start))) return Number(scheduled.travel_start);
    }

    // Compatibility fallback when a stale/old preview does not yet expose the
    // V2.6.2 source-position projection.
    return (drive?.segments || []).slice(0, segmentIndex).reduce((sum, item, index) => {
      const resolved = variables?.[`${drive?.name}.stroke${index + 1}`];
      const value = Number(resolved ?? item?.travel ?? 0);
      return sum + (Number.isFinite(value) ? value : 0);
    }, 0);
  }

  return {
    evaluateExpression,
    normalizeRows,
    runtimeRows,
    mappingNumber,
    mapPosition,
    mapDerivatives,
    inverseMapPosition,
    topLevelDifference,
    mappedTravelExpression,
    sourceSegmentStart,
  };
});
