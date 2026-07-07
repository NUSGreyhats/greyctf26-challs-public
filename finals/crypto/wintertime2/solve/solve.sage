import random
from hashlib import shake_256

from montgomery_isogenies.kummer_line import KummerLine
from montgomery_isogenies.kummer_isogeny import KummerLineIsogeny
from montgomery_isogenies.isogenies_x_only import lift_image_to_curve

from theta_structures.couple_point import CouplePoint
from theta_isogenies.product_isogeny import EllipticProductIsogeny

from utilities.discrete_log import BiDLP, discrete_log_pari
from utilities.supersingular import torsion_basis, torsion_basis_with_pairing


def eval_dimtwo_isog(Phi, q, P, Q, ord, RS=None):
    R1 = P
    R2 = Phi.domain()[1](0)
    phiP = Phi(CouplePoint(R1, R2))
    imP = phiP[0]

    R1 = Q
    R2 = Phi.domain()[1](0)
    phiQ = Phi(CouplePoint(R1, R2))
    imQ = phiQ[0]

    R1 = P-Q
    R2 = Phi.domain()[1](0)
    phiPQ = Phi(CouplePoint(R1, R2))
    imPQ = phiPQ[0]

    if (imP - imQ)[0] != imPQ[0]:
        imQ = -imQ


    if RS == None:
        R, S, WP = torsion_basis_with_pairing(Phi.domain()[1], ord)
    else:
        R, S = RS
        WP = R.weil_pairing(S, ord)

    R1 = Phi.domain()[0](0)
    R2 = R
    phiR = Phi(CouplePoint(R1, R2))
    imR = phiR[0]

    R1 = Phi.domain()[0](0)
    R2 = S
    phiS = Phi(CouplePoint(R1, R2))
    imS = phiS[0]

    R1 = Phi.domain()[0](0)
    R2 = R-S
    phiRS = Phi(CouplePoint(R1, R2))
    imRS = phiRS[0]

    if (imR - imS)[0] != imRS[0]:
        imS = -imS

    wp = WP^q
    x, y = BiDLP(imP, imR, imS, ord, ePQ=wp)
    w, z = BiDLP(imQ, imR, imS, ord, ePQ=wp)


    imP = x*R + y*S
    imQ = w*R + z*S

    imP *= q
    imQ *= q

    return imP, imQ


def xof_kdf(X, Y):
    """
    A simple key-derivation function which initalised an XOF from two
    finite field elements. A key is intended to then be derived from
    this by requesting len(key) bytes, see meth:xof_encrypt
    """
    X_bytes = X.to_bytes()
    Y_bytes = Y.to_bytes() 
    return shake_256(X_bytes + Y_bytes)

def xof_encrypt(xof, msg):
    """
    Compute the XOR encryption of a message by sampling
    len(msg) bytes from a suitible XOF.
    """
    key = xof.digest(len(msg))
    return bytes(x ^^ y for (x, y) in zip(key, msg))

a, b, c, f = 127, 162, 18, 9
A, B, C = 2**a, 3**b, 5**c
p = 4 * f * A * B * C - 1
x = C

FF.<xx> = GF(p)[]
F.<i> = GF(p^2, modulus=xx^2+1)
ct, pk, hint = load('chall.sobj')

# Recover delta
X_A, Y_A = hint
_, _, _, _, _, _, dX_A, dY_A = pk
e0 = X_A.weil_pairing(Y_A, C)
e1 = dX_A.weil_pairing(dY_A, C)
delta_squared = discrete_log(e1, e0, ord=C, operation='*') % C
rec_delta = 0
for k in range(1, c+1):
    for y in range(5):
        rec_delta += 5**(k-1)
        if (rec_delta**2 - delta_squared) % 5**k:
            continue
        break

# Recover deg
EB, P2_B, Q2_B, X_B, Y_B, EAB, P2_AB, Q2_AB, ct_bytes = ct
e0 = P2_B.weil_pairing(Q2_B, 4*A)
e1 = P2_AB.weil_pairing(Q2_AB, 4*A)
deg_squared = -discrete_log(e1, e0, ord=4*A, operation='*') % A
assert deg_squared % 8 == 1, 'e'
x = 1
for k in range(3, a): # hensel lift from mod8 to modA
    if ((x * x - deg_squared) >> k) & 1:
        x += (1 << (k - 1))
degs = [x % A, x + (A >> 1) % A]

for deg in degs:
    try:
        UAB, VAB, wp = torsion_basis_with_pairing(EAB, C)
        
        P, Q = CouplePoint(-deg * P2_B, P2_AB), CouplePoint(-deg * Q2_B, Q2_AB)
        kernel = (P, Q)
        Phi = EllipticProductIsogeny(kernel, a)

        X_AB, Y_AB = eval_dimtwo_isog(Phi, A-deg, X_B, Y_B, C, RS=(UAB, VAB))

        X_AB *= rec_delta
        Y_AB *= rec_delta

        xof = xof_kdf(X_AB[0], Y_AB[0])
        pt = xof_encrypt(xof, ct_bytes)
        print(pt)
    except ValueError:
        pass

# DRAG THIS FILE INTO DIST/ THEN RUN