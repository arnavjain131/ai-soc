import assert from 'node:assert/strict'
import test from 'node:test'
import { completeRecovery, recoveryCallback, recoveryExchange, recoveryRedirect, validateNewPassword } from '../src/accountRecovery.ts'

test('recovery only accepts a single code on the exact callback path and rejects implicit tokens', () => {
  assert.deepEqual(recoveryCallback('https://soc.test/auth/recovery?code=synthetic'), { code:'synthetic', error:false })
  for (const link of ['/auth/recovery', '/?code=synthetic', '/auth/recovery?code=a&code=b',
    '/auth/recovery?code=a#error=expired', '/auth/recovery?code=a&error=expired',
    '/auth/recovery#access_token=synthetic', '/auth/recovery?code=']) {
    assert.equal(recoveryCallback('https://soc.test' + link).code, null)
  }
})

test('recovery redirects use the current origin and fixed path, never a next parameter', () => {
  assert.equal(recoveryRedirect('https://soc.test/?next=https://elsewhere.test'), 'https://soc.test/auth/recovery')
  assert.equal(recoveryRedirect('http://127.0.0.1:5173'), 'http://127.0.0.1:5173/auth/recovery')
  assert.throws(() => recoveryRedirect('http://public.test'), /requires HTTPS/)
})

test('a valid PKCE recovery exchange is consumed once despite StrictMode effect replays', async () => {
  let calls = 0
  const exchange = recoveryExchange(async code => {
    calls++; assert.equal(code, 'synthetic')
    return { data:{ session:{}, redirectType:'recovery' }, error:null }
  }, { code:'synthetic', error:false })
  assert.deepEqual(await Promise.all([exchange(), exchange()]), [true,true])
  assert.equal(calls, 1)
})

test('existing sessions, non-recovery exchanges, missing links and failed codes never enable password update', async () => {
  for (const response of [{ data:{session:{}}, error:null },
    { data:{session:{},redirectType:'invite'}, error:null },
    { data:{session:null,redirectType:'recovery'},error:null },
    { data:{session:{},redirectType:'recovery'},error:new Error('private raw error') }]) {
    assert.equal(await recoveryExchange(async () => response, {code:'synthetic',error:false})(), false)
  }
  assert.equal(await recoveryExchange(async () => { throw new Error('must not exchange') }, {code:null,error:false})(),false)
  assert.equal(await recoveryExchange(async () => { throw new Error('raw failure') }, {code:'synthetic',error:false})(),false)
})

test('password length and confirmation are checked before contacting Auth', async () => {
  let calls = 0
  const auth={ updateUser:async () => { calls++; return {error:null} }, signOut:async () => ({error:null}) }
  for (const [value, confirmation] of [['short','short'], ['x'.repeat(129),'x'.repeat(129)], ['long-enough-password','different']]) {
    await assert.rejects(completeRecovery(auth,value,confirmation))
  }
  assert.equal(calls,0)
  assert.doesNotThrow(() => validateNewPassword('long-enough-password','long-enough-password'))
})

test('successful password update attempts global sign-out without returning the password', async () => {
  const steps=[]
  const result = await completeRecovery({
    updateUser:async attributes => { assert.equal(attributes.password,'synthetic-new-password'); steps.push('update'); return {error:null} },
    signOut:async options => { assert.deepEqual(options,{scope:'global'}); steps.push('signOut'); return {error:null} },
  },'synthetic-new-password','synthetic-new-password')
  assert.deepEqual(steps,['update','signOut']); assert.deepEqual(result,{signedOut:true})
})

test('Auth update failures are sanitized; sign-out failures preserve the successful update outcome', async () => {
  await assert.rejects(completeRecovery({updateUser:async () => ({error:new Error('private provider output')}),
    signOut:async () => { throw new Error('must not sign out') }}, 'synthetic-new-password','synthetic-new-password'),
    error => !error.message.includes('private provider output') && error.message.includes('could not be updated'))
  assert.deepEqual(await completeRecovery({updateUser:async () => ({error:null}),
    signOut:async () => { throw new Error('network failure') }}, 'synthetic-new-password','synthetic-new-password'),{signedOut:false})
})
