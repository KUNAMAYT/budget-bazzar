const headers = { 'Content-Type': 'application/json' };
let transactions = [];
let currentFilter = 'all';
let savingsStreak = Number(localStorage.getItem('budgetBazzarStreak') || 0);

const money = value => new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(value);
const escapeHtml = value => String(value).replace(/[&<>"']/g, char => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;' }[char]));

function speakWelcome() {
  if (!('speechSynthesis' in window) || sessionStorage.getItem('welcomeSpoken') === 'true') return;
  const speak = () => {
    const voices = window.speechSynthesis.getVoices();
    const preferredVoice = voices.find(voice => /female|samantha|zira|karen|susan|hazel|aria/i.test(voice.name + voice.voiceURI)) || voices.find(voice => /^en/i.test(voice.lang));
    const message = new SpeechSynthesisUtterance('Welcome to Budget Bazzar, the most affordable store on the web.');
    if (preferredVoice) message.voice = preferredVoice;
    message.rate = 0.92;
    message.pitch = 1.08;
    window.speechSynthesis.cancel();
    window.speechSynthesis.speak(message);
    sessionStorage.setItem('welcomeSpoken', 'true');
  };
  if (window.speechSynthesis.getVoices().length) speak();
  else window.speechSynthesis.addEventListener('voiceschanged', speak, { once: true });
  window.addEventListener('pointerdown', speak, { once: true });
}

async function loadTransactions() {
  const response = await fetch('/api/transactions', { headers });
  if (!response.ok) throw new Error('API key rejected');
  transactions = await response.json();
  document.querySelector('.status-dot').style.background = '#4b9b6d';
  document.querySelector('#statusText').textContent = 'API connected';
  render();
}

async function verifySession() {
  const response = await fetch('/api/auth/me', { headers });
  if (!response.ok) { window.location.href = '/login'; return false; }
  return true;
}

function render() {
  const income = transactions.filter(item => item.kind === 'income').reduce((sum, item) => sum + item.amount, 0);
  const expenses = transactions.filter(item => item.kind === 'expense').reduce((sum, item) => sum + item.amount, 0);
  document.querySelector('#balance').textContent = money(income - expenses);
  document.querySelector('#income').textContent = money(income);
  document.querySelector('#expenses').textContent = money(expenses);
  const filtered = currentFilter === 'all' ? transactions : transactions.filter(item => item.kind === currentFilter);
  const list = document.querySelector('#transactionList');
  list.innerHTML = filtered.length ? filtered.map(item => `<article class="transaction"><span class="transaction-icon ${item.kind}">${item.kind === 'income' ? '↗' : '↘'}</span><div><div class="transaction-title">${escapeHtml(item.title)}</div><div class="transaction-category">${escapeHtml(item.category)}</div></div><div><div class="transaction-amount ${item.kind}">${item.kind === 'income' ? '+' : '-'}${money(item.amount)}</div><div class="transaction-date">${escapeHtml(item.transaction_date)}</div></div><button class="delete-button" data-id="${item.id}" title="Delete transaction" aria-label="Delete transaction">×</button></article>`).join('') : '<div class="empty-state">Nothing here yet. Add your first transaction.</div>';
  document.querySelectorAll('.delete-button').forEach(button => button.addEventListener('click', () => removeTransaction(button.dataset.id)));
}

const guessChallenges = [
  { prompt: 'Which purchase keeps more money in your pocket?', options: ['$4 home coffee', '$18 delivery lunch', '$9 impulse gadget'], answer: 0 },
  { prompt: 'Which is the best small saving?', options: ['$2.50 reusable bottle', '$12 late fee', '$7 unused subscription'], answer: 0 },
  { prompt: 'Which choice is easiest to repeat every week?', options: ['$5 planned snack', '$25 last-minute order', '$15 random sale'], answer: 0 },
];
let guessRound = Math.floor(Math.random() * guessChallenges.length);

function setupGames() {
  const challenge = guessChallenges[guessRound];
  const prompt = document.querySelector('#guessPrompt');
  const options = document.querySelector('#guessOptions');
  if (!prompt || !options) return;
  prompt.textContent = challenge.prompt;
  options.innerHTML = challenge.options.map((option, index) => `<button class="guess-option" data-choice="${index}">${escapeHtml(option)}</button>`).join('');
  options.querySelectorAll('.guess-option').forEach(button => button.addEventListener('click', () => {
    const correct = Number(button.dataset.choice) === challenge.answer;
    document.querySelector('#guessResult').textContent = correct ? 'Smart pick. Your budget approves.' : 'Close one. Look for the choice you can repeat.';
    options.querySelectorAll('.guess-option').forEach(option => option.disabled = true);
    if (correct) button.classList.add('correct'); else button.classList.add('wrong');
  }));
  document.querySelector('#streakCount').textContent = savingsStreak;
  document.querySelector('#streakFill').style.width = `${Math.min(savingsStreak, 3) / 3 * 100}%`;
}

function addSavingsDay() {
  savingsStreak = Math.min(savingsStreak + 1, 3);
  localStorage.setItem('budgetBazzarStreak', savingsStreak);
  document.querySelector('#streakCount').textContent = savingsStreak;
  document.querySelector('#streakFill').style.width = `${savingsStreak / 3 * 100}%`;
  document.querySelector('#streakResult').textContent = savingsStreak === 3 ? 'Mini win unlocked: consistency beats intensity.' : `${3 - savingsStreak} more day${3 - savingsStreak === 1 ? '' : 's'} to unlock a mini win.`;
}

async function removeTransaction(id) {
  await fetch(`/api/transactions/${id}`, { method: 'DELETE', headers });
  await loadTransactions();
}

document.querySelector('#transactionForm').addEventListener('submit', async event => {
  event.preventDefault();
  const formData = new FormData(event.currentTarget);
  const payload = Object.fromEntries(formData.entries());
  payload.amount = Number(payload.amount);
  const response = await fetch('/api/transactions', { method: 'POST', headers, body: JSON.stringify(payload) });
  const message = document.querySelector('#formMessage');
  if (!response.ok) { message.textContent = 'Please check the transaction details.'; return; }
  event.currentTarget.reset();
  event.currentTarget.transaction_date.value = new Date().toISOString().slice(0, 10);
  message.textContent = 'Added to your ledger.';
  await loadTransactions();
});

document.querySelectorAll('.filter').forEach(button => button.addEventListener('click', () => {
  document.querySelector('.filter.active').classList.remove('active');
  button.classList.add('active');
  currentFilter = button.dataset.filter;
  render();
}));
document.querySelector('#refreshButton').addEventListener('click', loadTransactions);
document.querySelector('#logoutButton').addEventListener('click', async () => {
  await fetch('/api/auth/logout', { method: 'POST', headers });
  window.location.href = '/login';
});
document.querySelector('[name="transaction_date"]').value = new Date().toISOString().slice(0, 10);
speakWelcome();
setupGames();
document.querySelector('#coinButton').addEventListener('click', addSavingsDay);
verifySession().then(ready => ready && loadTransactions()).catch(() => { document.querySelector('#statusText').textContent = 'API key required'; document.querySelector('#transactionList').innerHTML = '<div class="empty-state">Could not connect. Reload and enter a valid API key.</div>'; });
