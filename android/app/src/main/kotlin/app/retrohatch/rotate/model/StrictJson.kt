package app.retrohatch.rotate.model

import java.nio.ByteBuffer
import java.nio.charset.CodingErrorAction

/** Raised for anything the trust layer refuses. The message is shown to the user as the reason. */
class TrustException(message: String) : Exception(message)

/**
 * Strict JSON, same rules as tools/trust.py `strict_loads` / `canonical` (and the Nano's native parser):
 * UTF-8 only, no BOM, no duplicate keys, no NaN/Infinity, no floats, no negative numbers, integers <= 2^31-1.
 * Values: Map<String, Any?> (insertion ordered), List<Any?>, String, Long, Boolean, null.
 */
object StrictJson {
    const val MAX_INT = 2147483647L
    private const val MAX_PARSE_DEPTH = 64

    fun parse(bytes: ByteArray): Any? {
        val text = try {
            Charsets.UTF_8.newDecoder().onMalformedInput(CodingErrorAction.REPORT).onUnmappableCharacter(CodingErrorAction.REPORT)
                .decode(ByteBuffer.wrap(bytes)).toString()
        } catch (e: java.nio.charset.CharacterCodingException) {
            throw TrustException("malformed JSON: not UTF-8")
        }
        if (text.startsWith("﻿")) throw TrustException("malformed JSON: byte order mark")
        return Parser(text).run()
    }

    fun parseObject(bytes: ByteArray): Map<String, Any?> {
        @Suppress("UNCHECKED_CAST")
        return parse(bytes) as? Map<String, Any?> ?: throw TrustException("JSON document is not an object")
    }

    /** json.dumps(doc, sort_keys=True, separators=(",", ":"), ensure_ascii=True) */
    fun canonical(v: Any?): ByteArray {
        val sb = StringBuilder()
        write(v, sb)
        return sb.toString().toByteArray(Charsets.US_ASCII)
    }

    private fun write(v: Any?, sb: StringBuilder) {
        when (v) {
            null -> sb.append("null")
            is Boolean -> sb.append(if (v) "true" else "false")
            is Long -> sb.append(v)
            is Int -> sb.append(v)
            is String -> writeString(v, sb)
            is List<*> -> {
                sb.append('[')
                v.forEachIndexed { i, x -> if (i > 0) sb.append(','); write(x, sb) }
                sb.append(']')
            }
            is Map<*, *> -> {
                sb.append('{')
                val keys = v.keys.map { it as String }.sortedWith(CODE_POINT_ORDER)
                keys.forEachIndexed { i, k -> if (i > 0) sb.append(','); writeString(k, sb); sb.append(':'); write(v[k], sb) }
                sb.append('}')
            }
            else -> throw TrustException("cannot serialise ${v.javaClass.simpleName}")
        }
    }

    // Python sorts str by code point; UTF-16 order differs only above the BMP.
    private val CODE_POINT_ORDER = Comparator<String> { a, b ->
        var i = 0; var j = 0
        while (i < a.length && j < b.length) {
            val ca = a.codePointAt(i); val cb = b.codePointAt(j)
            if (ca != cb) return@Comparator ca.compareTo(cb)
            i += Character.charCount(ca); j += Character.charCount(cb)
        }
        (a.length - i).compareTo(b.length - j)
    }

    private fun writeString(s: String, sb: StringBuilder) {
        sb.append('"')
        for (c in s) {
            when {
                c == '"' -> sb.append("\\\"")
                c == '\\' -> sb.append("\\\\")
                c == '\n' -> sb.append("\\n")
                c == '\r' -> sb.append("\\r")
                c == '\t' -> sb.append("\\t")
                c == '\b' -> sb.append("\\b")
                c == '\u000C' -> sb.append("\\f")
                c in ' '..'~' -> sb.append(c)
                else -> sb.append("\\u").append(String.format("%04x", c.code))   // ensure_ascii: everything outside space..~
            }
        }
        sb.append('"')
    }

    private class Parser(val s: String) {
        var i = 0

        fun run(): Any? {
            ws()
            val v = value(0)
            ws()
            if (i != s.length) fail("trailing data")
            return v
        }

        fun fail(why: String): Nothing = throw TrustException("malformed JSON: $why")

        fun ws() { while (i < s.length && (s[i] == ' ' || s[i] == '\t' || s[i] == '\n' || s[i] == '\r')) i++ }

        fun value(depth: Int): Any? {
            if (depth > MAX_PARSE_DEPTH) fail("too deep")
            if (i >= s.length) fail("unexpected end")
            return when (val c = s[i]) {
                '{' -> obj(depth)
                '[' -> arr(depth)
                '"' -> str()
                't' -> lit("true", true)
                'f' -> lit("false", false)
                'n' -> lit("null", null)
                'N', 'I' -> throw TrustException("disallowed number 'NaN or Infinity'")
                else -> if (c == '-' || c in '0'..'9') num() else fail("unexpected '$c'")
            }
        }

        fun lit(word: String, v: Any?): Any? {
            if (!s.startsWith(word, i)) fail("bad literal")
            i += word.length
            return v
        }

        fun num(): Long {
            val st = i
            if (s[i] == '-') i++
            if (i >= s.length || s[i] !in '0'..'9') fail("bad number")
            if (s[i] == '0') i++ else while (i < s.length && s[i] in '0'..'9') i++
            var isInt = true
            if (i < s.length && s[i] == '.') { isInt = false; i++; while (i < s.length && s[i] in '0'..'9') i++ }
            if (i < s.length && (s[i] == 'e' || s[i] == 'E')) { isInt = false; i++; if (i < s.length && (s[i] == '+' || s[i] == '-')) i++; while (i < s.length && s[i] in '0'..'9') i++ }
            val tok = s.substring(st, i)
            if (!isInt || tok.startsWith("-")) throw TrustException("disallowed number '$tok'")
            val v = tok.toBigInteger()
            if (v > MAX_INT.toBigInteger()) throw TrustException("disallowed number '$tok'")
            return v.toLong()
        }

        fun str(): String {
            i++ // opening quote
            val sb = StringBuilder()
            while (true) {
                if (i >= s.length) fail("unterminated string")
                val c = s[i++]
                when {
                    c == '"' -> return sb.toString()
                    c < ' ' -> fail("control character in string")
                    c == '\\' -> {
                        if (i >= s.length) fail("bad escape")
                        when (val e = s[i++]) {
                            '"' -> sb.append('"'); '\\' -> sb.append('\\'); '/' -> sb.append('/')
                            'b' -> sb.append('\b'); 'f' -> sb.append('\u000C'); 'n' -> sb.append('\n'); 'r' -> sb.append('\r'); 't' -> sb.append('\t')
                            'u' -> {
                                if (i + 4 > s.length) fail("bad escape")
                                val h = s.substring(i, i + 4)
                                if (!h.all { it in '0'..'9' || it in 'a'..'f' || it in 'A'..'F' }) fail("bad escape")
                                sb.append(h.toInt(16).toChar()); i += 4
                            }
                            else -> fail("bad escape '\\$e'")
                        }
                    }
                    else -> sb.append(c)
                }
            }
        }

        fun arr(depth: Int): List<Any?> {
            i++
            val out = ArrayList<Any?>()
            ws()
            if (i < s.length && s[i] == ']') { i++; return out }
            while (true) {
                ws(); out.add(value(depth + 1)); ws()
                if (i >= s.length) fail("unterminated array")
                if (s[i] == ',') { i++; continue }
                if (s[i] == ']') { i++; return out }
                fail("expected , or ]")
            }
        }

        fun obj(depth: Int): Map<String, Any?> {
            i++
            val out = LinkedHashMap<String, Any?>()
            ws()
            if (i < s.length && s[i] == '}') { i++; return out }
            while (true) {
                ws()
                if (i >= s.length || s[i] != '"') fail("expected key")
                val k = str()
                if (out.containsKey(k)) throw TrustException("duplicate key '$k'")
                ws()
                if (i >= s.length || s[i] != ':') fail("expected :")
                i++; ws()
                out[k] = value(depth + 1); ws()
                if (i >= s.length) fail("unterminated object")
                if (s[i] == ',') { i++; continue }
                if (s[i] == '}') { i++; return out }
                fail("expected , or }")
            }
        }
    }
}
