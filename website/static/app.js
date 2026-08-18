document.addEventListener('DOMContentLoaded', () => {
  const THEME_KEY = 'mufakkir.theme';
  const THEME_COOKIE = 'mufakkir_theme';
  const root = document.documentElement;
  const themeMeta = document.querySelector('meta[name="theme-color"]');
  const themeToggle = document.querySelector('[data-theme-toggle]');

  const readCookie = (name) => {
    const parts = (`; ${document.cookie}`).split(`; ${name}=`);
    if (parts.length < 2) return '';
    return decodeURIComponent(parts.pop().split(';').shift() || '').trim().toLowerCase();
  };
  const persistTheme = (theme) => {
    try {
      localStorage.setItem(THEME_KEY, theme);
    } catch (_error) {
      /* ignore private mode */
    }
    document.cookie = `${THEME_COOKIE}=${theme}; Path=/; Max-Age=31536000; SameSite=Lax`;
  };
  const readTheme = () => {
    const fromCookie = readCookie(THEME_COOKIE);
    if (fromCookie === 'dark' || fromCookie === 'light') return fromCookie;
    try {
      const saved = localStorage.getItem(THEME_KEY);
      if (saved === 'dark' || saved === 'light') return saved;
    } catch (_error) {
      /* ignore private mode */
    }
    return root.getAttribute('data-theme') === 'dark' ? 'dark' : 'light';
  };
  const applyTheme = (theme, persist) => {
    const next = theme === 'dark' ? 'dark' : 'light';
    root.setAttribute('data-theme', next);
    root.style.colorScheme = next;
    if (themeMeta) themeMeta.setAttribute('content', next === 'dark' ? '#07090b' : '#f5f6f8');
    if (themeToggle) {
      themeToggle.setAttribute('aria-checked', next === 'dark' ? 'true' : 'false');
      themeToggle.classList.toggle('is-dark', next === 'dark');
    }
    if (persist) persistTheme(next);
  };

  applyTheme(readTheme(), false);
  if (themeToggle) {
    themeToggle.addEventListener('click', () => {
      const next = root.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
      applyTheme(next, true);
    });
  }

  const navToggle = document.querySelector('.nav-toggle');
  const nav = document.getElementById('mainNav');
  if (navToggle && nav) {
    navToggle.addEventListener('click', () => {
      const open = nav.classList.toggle('open');
      navToggle.setAttribute('aria-expanded', open ? 'true' : 'false');
    });
  }

  document.querySelectorAll('.account-menu').forEach((menu) => {
    menu.addEventListener('toggle', () => {
      if (!menu.open) return;
      document.querySelectorAll('.account-menu').forEach((other) => {
        if (other !== menu) other.removeAttribute('open');
      });
    });
  });
  document.addEventListener('click', (event) => {
    document.querySelectorAll('.account-menu[open]').forEach((menu) => {
      if (!menu.contains(event.target)) menu.removeAttribute('open');
    });
  });

  document.querySelectorAll('[data-password-toggle]').forEach((button) => {
    button.addEventListener('click', () => {
      const field = button.closest('.password-field');
      const input = field && field.querySelector('input');
      if (!input) return;
      const show = input.type === 'password';
      input.type = show ? 'text' : 'password';
      button.textContent = show ? 'إخفاء' : 'إظهار';
      button.setAttribute('aria-pressed', show ? 'true' : 'false');
    });
  });

  document.querySelectorAll('[data-department-filter]').forEach((form) => {
    const select = form.querySelector('select[name="department"]');
    if (!select) return;
    select.addEventListener('change', () => {
      form.submit();
    });
  });

  document.querySelectorAll('[data-copy]').forEach((button) => {
    button.addEventListener('click', async (event) => {
      event.preventDefault();
      event.stopPropagation();
      const value = button.getAttribute('data-copy') || '';
      if (!value) return;
      const restore = button.textContent;
      try {
        await navigator.clipboard.writeText(value);
        button.textContent = 'تم النسخ';
      } catch (_error) {
        const helper = document.createElement('textarea');
        helper.value = value;
        document.body.appendChild(helper);
        helper.select();
        document.execCommand('copy');
        helper.remove();
        button.textContent = 'تم النسخ';
      }
      window.setTimeout(() => {
        button.textContent = restore;
      }, 1600);
    });
  });

  const decisionForm = document.querySelector('[data-decision-form]');
  const decisionDialog = document.querySelector('[data-decision-dialog]');
  if (decisionForm && decisionDialog) {
    const confirmText = decisionDialog.querySelector('[data-confirm-text]');
    const yesBtn = decisionDialog.querySelector('[data-confirm-yes]');
    const noBtn = decisionDialog.querySelector('[data-confirm-no]');
    const prompts = {
      adopted: 'هل تعتمد هذا المقترح؟',
      rejected: 'هل ترفض هذا المقترح؟',
      modified: 'هل تطلب تعديل هذا المقترح؟',
    };
    decisionForm.addEventListener('submit', (event) => {
      if (decisionForm.dataset.confirmed === '1') return;
      event.preventDefault();
      const decision = (decisionForm.decision && decisionForm.decision.value) || 'adopted';
      if (confirmText) confirmText.textContent = prompts[decision] || prompts.adopted;
      if (typeof decisionDialog.showModal === 'function') {
        decisionDialog.showModal();
      } else {
        decisionForm.dataset.confirmed = '1';
        decisionForm.submit();
      }
    });
    if (yesBtn) {
      yesBtn.addEventListener('click', () => {
        decisionForm.dataset.confirmed = '1';
        if (typeof decisionDialog.close === 'function') decisionDialog.close();
        decisionForm.submit();
      });
    }
    if (noBtn) {
      noBtn.addEventListener('click', () => {
        if (typeof decisionDialog.close === 'function') decisionDialog.close();
      });
    }
  }

  const form = document.querySelector('[data-loading-form]');
  const submitPanel = document.getElementById('submitPanel');
  const waitPanel = document.getElementById('waitPanel');
  const waitStatus = document.getElementById('waitStatus');
  const waitCase = document.querySelector('[data-wait-case]');
  const waitTimer = document.querySelector('[data-wait-timer]');
  const waitMeter = document.querySelector('[data-wait-meter]');
  const waitTip = document.querySelector('[data-wait-tip]');
  const waitLog = document.querySelector('[data-wait-log]');
  const waitSteps = Array.from(document.querySelectorAll('[data-wait-step]'));
  const statusBox = document.getElementById('modelStatus');
  const STAGE_LABELS = {
    understanding: 'نقرأ كلامك كما كتبته',
    problem: 'نرتّب الوضع الحالي وأثره',
    proposal: 'نبني الخيارات والتوصية',
    ready: 'نجهّز صفحة النتيجة',
  };
  const STAGE_PROGRESS = {
    understanding: 22,
    problem: 48,
    proposal: 72,
    ready: 92,
  };
  const WAIT_TIPS = [
    'التحليل العميق يأخذ عادة دقيقة إلى دقيقتين. أنت في المكان الصحيح.',
    'التوصية مساعدة للمدير، وليست اعتمادًا تلقائيًا.',
    'حتى لو ما كتبت حلًا، مُفكّر يبني أربع طرق للتعامل.',
    'الموارد والقيود التي كتبتها تدخل في التوصية إن وُجدت.',
    'بعد التحليل يصل المقترح للوحة المدير بانتظار القرار.',
  ];
  const WAIT_LOGS = [
    'نفصل العنوان عن وصف الوضع',
    'نبحث عن أثر العمل على المراجعين أو القسم',
    'نرتّب حلًا سريعًا يمكن التراجع عنه',
    'نفحص إن كان السبب يحتاج تحققًا أولًا',
    'نضع فكرة الموظف ضمن الخيارات إن وُجدت',
    'نجهّز شرط تنفيذ واضح للمدير',
  ];
  const RESULT_PATH = /^\/result\/[0-9a-f]{32}$/i;
  const DRAFT_KEY = 'mufakkir.submitDraft.v1';
  const DRAFT_FIELDS = ['department', 'title', 'problem', 'employee_suggestion', 'resources', 'constraints'];
  let busy = false;
  let waitStartedAt = 0;
  let waitProgress = 8;
  let waitTimers = [];
  let waitTipIndex = 0;
  let waitLogIndex = 0;
  const STAGE_ORDER = ['understanding', 'problem', 'proposal', 'ready'];

  const prefersReducedMotion = () => window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  const formatElapsed = (ms) => {
    const total = Math.max(0, Math.floor(ms / 1000));
    const minutes = Math.floor(total / 60);
    const seconds = String(total % 60).padStart(2, '0');
    return `${minutes}:${seconds}`;
  };

  const setMeter = (value) => {
    waitProgress = Math.max(waitProgress, Math.min(96, value));
    if (waitMeter) waitMeter.style.width = `${waitProgress}%`;
  };

  const setStatus = (label) => {
    if (!waitStatus || !label) return;
    waitStatus.innerHTML = `${label}<span class="wait-dots" aria-hidden="true"></span>`;
  };

  const setWaitStep = (stage) => {
    const current = STAGE_ORDER.indexOf(stage);
    waitSteps.forEach((item) => {
      const index = STAGE_ORDER.indexOf(item.getAttribute('data-wait-step'));
      item.classList.toggle('is-on', index === current);
      item.classList.toggle('is-done', current >= 0 && index < current);
    });
    if (STAGE_PROGRESS[stage]) setMeter(STAGE_PROGRESS[stage]);
  };

  const pushWaitLog = (text) => {
    if (!waitLog || !text) return;
    const line = document.createElement('li');
    line.textContent = text;
    waitLog.appendChild(line);
    while (waitLog.children.length > 4) waitLog.removeChild(waitLog.firstChild);
  };

  const stopWaitTheater = () => {
    waitTimers.forEach((id) => window.clearInterval(id));
    waitTimers = [];
    document.body.classList.remove('is-waiting');
  };

  const startWaitTheater = (title, department) => {
    stopWaitTheater();
    waitStartedAt = Date.now();
    waitProgress = 8;
    waitTipIndex = 0;
    waitLogIndex = 0;
    document.body.classList.add('is-waiting');
    if (waitCase) {
      const bits = [title, department].filter(Boolean);
      waitCase.textContent = bits.length ? bits.join(' — ') : '';
    }
    if (waitLog) waitLog.replaceChildren();
    if (waitTimer) waitTimer.textContent = '0:00';
    setMeter(8);
    setWaitStep('understanding');
    setStatus(STAGE_LABELS.understanding);
    if (waitTip) waitTip.textContent = WAIT_TIPS[0];
    pushWaitLog(WAIT_LOGS[0]);
    waitTimers.push(window.setInterval(() => {
      if (waitTimer) waitTimer.textContent = formatElapsed(Date.now() - waitStartedAt);
      setMeter(waitProgress + 0.18);
    }, 250));
    waitTimers.push(window.setInterval(() => {
      waitTipIndex = (waitTipIndex + 1) % WAIT_TIPS.length;
      if (waitTip) waitTip.textContent = WAIT_TIPS[waitTipIndex];
    }, 7000));
    waitTimers.push(window.setInterval(() => {
      waitLogIndex = (waitLogIndex + 1) % WAIT_LOGS.length;
      pushWaitLog(WAIT_LOGS[waitLogIndex]);
    }, 4200));
  };

  const lockForm = (locked) => {
    if (!form) return;
    form.setAttribute('aria-busy', locked ? 'true' : 'false');
    form.querySelectorAll('input, select, textarea, button').forEach((el) => {
      el.disabled = locked;
    });
  };

  const showWait = (title, department) => {
    if (submitPanel) submitPanel.hidden = true;
    if (!waitPanel) return;
    waitPanel.hidden = false;
    waitPanel.classList.remove('is-leaving');
    startWaitTheater(title, department);
    requestAnimationFrame(() => waitPanel.classList.add('is-visible'));
  };

  const hideWait = () => {
    stopWaitTheater();
    if (waitPanel) {
      waitPanel.classList.remove('is-visible', 'is-leaving');
      waitPanel.hidden = true;
    }
    if (submitPanel) submitPanel.hidden = false;
  };

  const leaveToResult = (path) => {
    setWaitStep('ready');
    setStatus(STAGE_LABELS.ready);
    setMeter(100);
    if (waitMeter) waitMeter.style.width = '100%';
    if (waitPanel) waitPanel.classList.add('is-leaving');
    const delay = prefersReducedMotion() ? 0 : 520;
    window.setTimeout(() => {
      stopWaitTheater();
      window.location.href = path;
    }, delay);
  };

  const readNdjson = async (response, onEvent) => {
    if (!response.body || !response.body.getReader) {
      const payload = await response.json();
      onEvent(payload);
      return;
    }
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() || '';
      lines.forEach((line) => {
        const trimmed = line.trim();
        if (!trimmed) return;
        onEvent(JSON.parse(trimmed));
      });
    }
    if (buffer.trim()) onEvent(JSON.parse(buffer.trim()));
  };

  if (statusBox) {
    fetch('/api/health')
      .then(async (response) => {
        const payload = await response.json();
        statusBox.textContent = payload.ok ? 'مُفكر جاهز يفكر معك.' : 'مُفكر يحتاج لحظة استعداد. أعد المحاولة بعد قليل.';
        statusBox.className = payload.ok ? 'notice info' : 'notice warning';
      })
      .catch(() => {
        statusBox.textContent = 'تعذر التواصل مع مُفكر الآن.';
        statusBox.className = 'notice warning';
      });
  }

  if (!form) {
    return;
  }

  const readDraftValues = () => {
    const values = {};
    DRAFT_FIELDS.forEach((name) => {
      if (form[name]) values[name] = form[name].value || '';
    });
    return values;
  };
  const writeDraft = () => {
    try {
      localStorage.setItem(DRAFT_KEY, JSON.stringify({ savedAt: Date.now(), values: readDraftValues() }));
    } catch (_error) {
      /* ignore quota / private mode */
    }
  };
  const restoreDraft = () => {
    const hasServerValues = DRAFT_FIELDS.some((name) => form[name] && String(form[name].value || '').trim());
    if (hasServerValues) return;
    try {
      const raw = localStorage.getItem(DRAFT_KEY);
      if (!raw) return;
      const parsed = JSON.parse(raw);
      const values = parsed && parsed.values ? parsed.values : {};
      DRAFT_FIELDS.forEach((name) => {
        if (form[name] && values[name]) form[name].value = values[name];
      });
    } catch (_error) {
      /* ignore broken drafts */
    }
  };
  const requiredFilled = () => Boolean(
    String(form.department && form.department.value || '').trim()
    && String(form.title && form.title.value || '').trim()
    && String(form.problem && form.problem.value || '').trim()
  );
  const clearDraft = () => {
    try {
      localStorage.removeItem(DRAFT_KEY);
    } catch (_error) {
      /* ignore */
    }
  };

  restoreDraft();
  let draftTimer = null;
  form.addEventListener('input', () => {
    window.clearTimeout(draftTimer);
    draftTimer = window.setTimeout(writeDraft, 400);
  });
  const saveDraftBtn = form.querySelector('[data-save-draft]');
  if (saveDraftBtn) {
    saveDraftBtn.addEventListener('click', writeDraft);
  }

  if (form.hasAttribute('data-wizard')) {
    const steps = Array.from(form.querySelectorAll('[data-step]'));
    const tabs = Array.from(document.querySelectorAll('[data-step-tab]'));
    const nextBtn = form.querySelector('[data-wizard-next]');
    const prevBtn = form.querySelector('[data-wizard-prev]');
    const submitBtn = form.querySelector('[data-wizard-submit]');
    const bar = document.querySelector('[data-wizard-bar]');
    const label = document.querySelector('[data-wizard-label]');
    const total = steps.length || 3;
    let current = 1;
    const showStep = (index) => {
      current = Math.min(total, Math.max(1, index));
      steps.forEach((step) => {
        const n = Number(step.getAttribute('data-step'));
        step.classList.toggle('is-active', n === current);
      });
      tabs.forEach((tab) => {
        const n = Number(tab.getAttribute('data-step-tab'));
        tab.classList.toggle('is-active', n === current);
        tab.classList.toggle('is-done', n < current);
      });
      if (bar) bar.style.width = `${Math.round((current / total) * 100)}%`;
      if (label) label.textContent = `الخطوة ${current} من ${total}`;
      form.classList.toggle('is-last-step', current === total);
      if (prevBtn) prevBtn.hidden = current === 1;
      if (nextBtn) nextBtn.hidden = current === total;
      if (submitBtn) submitBtn.disabled = current !== total || !requiredFilled();
    };
    const validateStep = (index) => {
      const panel = form.querySelector(`[data-step="${index}"]`);
      if (!panel) return true;
      const fields = panel.querySelectorAll('input, select, textarea');
      for (const el of fields) {
        if (!el.checkValidity()) {
          el.reportValidity();
          return false;
        }
      }
      return true;
    };
    if (nextBtn) {
      nextBtn.hidden = false;
      nextBtn.addEventListener('click', () => {
        if (!validateStep(current)) return;
        showStep(current + 1);
      });
    }
    if (prevBtn) {
      prevBtn.addEventListener('click', () => showStep(current - 1));
    }
    form.classList.add('is-wizard-ready');
    form.addEventListener('input', () => {
      if (submitBtn) submitBtn.disabled = current !== total || !requiredFilled();
    });
    showStep(1);
  }

  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    if (busy) return;
    if (!requiredFilled()) {
      const focusEl = !String(form.department.value || '').trim()
        ? form.department
        : (!String(form.title.value || '').trim() ? form.title : form.problem);
      if (focusEl.reportValidity) focusEl.reportValidity();
      else focusEl.focus();
      return;
    }
    busy = true;
    lockForm(true);
    const body = {
      csrf_token: form.csrf_token.value,
      department: form.department.value,
      title: form.title.value,
      problem: form.problem.value,
      employee_suggestion: form.employee_suggestion.value,
      resources: form.resources.value,
      constraints: form.constraints.value,
    };
    showWait(body.title, body.department);

    try {
      const response = await fetch('/api/analyze', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Accept: 'application/x-ndjson, application/json',
        },
        body: JSON.stringify(body),
      });
      const type = (response.headers.get('content-type') || '').toLowerCase();
      let finalEvent = null;
      const handleEvent = (payload) => {
        if (payload && payload.stage && STAGE_LABELS[payload.stage]) {
          setWaitStep(payload.stage);
          setStatus(STAGE_LABELS[payload.stage]);
          return;
        }
        finalEvent = payload;
      };
      if (type.includes('ndjson')) {
        await readNdjson(response, handleEvent);
      } else {
        handleEvent(await response.json());
      }
      const payload = finalEvent || {};
      if (payload.redirect && RESULT_PATH.test(payload.redirect)) {
        clearDraft();
        leaveToResult(payload.redirect);
        return;
      }
      const detail = Array.isArray(payload.detail)
        ? payload.detail.map((item) => item.msg).join(' ')
        : payload.detail;
      throw new Error((payload.errors && payload.errors[0]) || payload.error || detail || 'تعذر تحليل المقترح.');
    } catch (error) {
      busy = false;
      lockForm(false);
      hideWait();
      const notice = document.createElement('div');
      notice.className = 'notice danger';
      notice.textContent = error.message || 'تعذر الاتصال بخادم التحليل.';
      form.parentElement.insertBefore(notice, form);
    }
  });
});
