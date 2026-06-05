package utils

import "regexp"

var obfuscationKey = [...]byte{0x2d, 0x57, 0x13, 0x68, 0x41, 0x22, 0x7a, 0x19}

// RevealString reconstructs compile-time obfuscated strings at runtime so
// sensitive defaults do not appear in the final binary as plaintext.
func RevealString(encoded []byte) string {
	decoded := make([]byte, len(encoded))
	for i, b := range encoded {
		mask := obfuscationKey[i%len(obfuscationKey)] ^ byte(i*17+31)
		decoded[i] = b ^ mask
	}
	return string(decoded)
}

func MustRevealRegexp(encoded []byte) *regexp.Regexp {
	return regexp.MustCompile(RevealString(encoded))
}
