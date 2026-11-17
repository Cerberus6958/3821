"""Checks the dispatch-rule theorem (5 + |lambda| - 1/m, and 5 - 3/m for FIFO) against the exact optimum on 7,000 random days."""
import random
from hub_exp import opt, dispatch
rng=random.Random(11); cnt=0; worst=0; bad=0
for it in range(7000):
    n=rng.randint(2,6); m=rng.randint(1,3); T=rng.choice([3,8,15,30])
    J=[]
    for _ in range(n):
        s=(rng.randint(0,9),rng.randint(0,9)); w=(rng.randint(0,9),rng.randint(0,9))
        a=abs(s[0]-5)+abs(s[1]-5)+abs(s[0]-w[0])+abs(s[1]-w[1]); b=abs(w[0]-5)+abs(w[1]-5)
        if a==0: a=1; 
        J.append((rng.randint(0,T),a,a+b))
    o=opt(J,m)
    for l in (-2,-1,-0.5,0,0.5,1,2):
        mx,_=dispatch(J,m,lambda x,l=l:x[0]+l*x[1]); r=mx/o; cnt+=1
        if r>worst: worst=r; wl=(l,m,J)
        if r>5+abs(l)-1/m+1e-9 or (l==0 and r>5-3/m+1e-9): bad+=1
print(cnt,worst,bad,wl)
