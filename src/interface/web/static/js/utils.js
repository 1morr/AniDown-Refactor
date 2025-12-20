/**
 * 全局工具函数库
 *
 * 提供可复用的JavaScript工具函数，包括Flash消息、日期格式化、
 * HTML转义、Modal管理等功能
 */

/**
 * 显示Flash消息
 * @param {string} category - 消息类型: 'success', 'error', 'warning', 'info'
 * @param {string} message - 消息内容
 * @param {number} duration - 显示时长（毫秒），默认5000ms
 */
function showFlashMessage(category, message, duration = 5000) {
  let flashContainer = document.getElementById('flash-messages');

  if (!flashContainer) {
    flashContainer = document.createElement('div');
    flashContainer.id = 'flash-messages';
    flashContainer.className = 'fixed top-20 right-4 z-50 space-y-2';
    document.body.appendChild(flashContainer);
  }

  const messageDiv = document.createElement('div');
  const colors = {
    success: 'border-green-500 bg-green-50 dark:bg-green-900/20 text-green-800 dark:text-green-300',
    error: 'border-red-500 bg-red-50 dark:bg-red-900/20 text-red-800 dark:text-red-300',
    warning: 'border-yellow-500 bg-yellow-50 dark:bg-yellow-900/20 text-yellow-800 dark:text-yellow-300',
    info: 'border-blue-500 bg-blue-50 dark:bg-blue-900/20 text-blue-800 dark:text-blue-300'
  };

  const icons = {
    success: 'fa-check-circle text-green-500',
    error: 'fa-exclamation-circle text-red-500',
    warning: 'fa-exclamation-triangle text-yellow-500',
    info: 'fa-info-circle text-blue-500'
  };

  messageDiv.className = `rounded-lg p-4 border-l-4 max-w-sm shadow-lg ${colors[category] || colors.info}
                          transition-all duration-300 transform translate-x-0 opacity-100`;
  messageDiv.innerHTML = `
    <div class="flex items-center gap-3">
      <i class="fas ${icons[category] || icons.info} text-lg"></i>
      <span class="text-sm font-medium">${escapeHtml(message)}</span>
      <button onclick="this.parentElement.parentElement.remove()"
              class="ml-auto text-current opacity-50 hover:opacity-100 transition-opacity">
        <i class="fas fa-times"></i>
      </button>
    </div>
  `;

  flashContainer.appendChild(messageDiv);

  // 自动移除
  setTimeout(() => {
    messageDiv.style.opacity = '0';
    messageDiv.style.transform = 'translateX(100%)';
    setTimeout(() => messageDiv.remove(), 300);
  }, duration);
}

/**
 * 格式化日期
 * @param {string|Date} dateString - ISO日期字符串或Date对象
 * @param {string} format - 格式: 'datetime', 'date', 'time', 'relative'
 * @returns {string} 格式化后的日期字符串
 */
function formatDate(dateString, format = 'datetime') {
  if (!dateString) return '-';

  const date = new Date(dateString);
  if (isNaN(date.getTime())) return '-';

  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  const hours = String(date.getHours()).padStart(2, '0');
  const minutes = String(date.getMinutes()).padStart(2, '0');
  const seconds = String(date.getSeconds()).padStart(2, '0');

  switch (format) {
    case 'date':
      return `${year}-${month}-${day}`;
    case 'time':
      return `${hours}:${minutes}:${seconds}`;
    case 'relative':
      return formatRelativeTime(date);
    case 'datetime':
    default:
      return `${year}-${month}-${day} ${hours}:${minutes}:${seconds}`;
  }
}

/**
 * 格式化相对时间（如"3分钟前"）
 * @param {Date} date - 日期对象
 * @returns {string} 相对时间描述
 */
function formatRelativeTime(date) {
  const now = new Date();
  const diffMs = now - date;
  const diffSec = Math.floor(diffMs / 1000);
  const diffMin = Math.floor(diffSec / 60);
  const diffHour = Math.floor(diffMin / 60);
  const diffDay = Math.floor(diffHour / 24);

  if (diffSec < 60) return '刚刚';
  if (diffMin < 60) return `${diffMin}分钟前`;
  if (diffHour < 24) return `${diffHour}小时前`;
  if (diffDay < 7) return `${diffDay}天前`;
  return formatDate(date, 'date');
}

/**
 * 转义HTML特殊字符，防止XSS攻击
 * @param {string} text - 待转义的文本
 * @returns {string} 转义后的文本
 */
function escapeHtml(text) {
  if (!text) return '';
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

/**
 * 转义JavaScript字符串中的特殊字符
 * @param {string} text - 待转义的文本
 * @returns {string} 转义后的文本
 */
function escapeJs(text) {
  if (!text) return '';
  return text
    .replace(/\\/g, '\\\\')
    .replace(/'/g, "\\'")
    .replace(/"/g, '\\"')
    .replace(/\n/g, '\\n')
    .replace(/\r/g, '\\r')
    .replace(/\t/g, '\\t');
}

/**
 * 格式化文件大小
 * @param {number} bytes - 字节数
 * @param {number} decimals - 小数位数，默认2位
 * @returns {string} 格式化后的大小（如"1.23 GB"）
 */
function formatFileSize(bytes, decimals = 2) {
  if (!bytes || bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB', 'PB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(decimals)) + ' ' + sizes[i];
}

/**
 * 格式化百分比
 * @param {number} value - 数值（0-100）
 * @param {number} decimals - 小数位数，默认1位
 * @returns {string} 格式化后的百分比（如"85.5%"）
 */
function formatPercentage(value, decimals = 1) {
  if (value === null || value === undefined) return '-';
  return parseFloat(value).toFixed(decimals) + '%';
}

/**
 * 简单的Modal管理器
 */
const ModalManager = {
  /**
   * 打开Modal
   * @param {string} modalId - Modal元素的ID
   */
  open(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) {
      modal.classList.remove('hidden');
      modal.classList.add('flex');
      document.body.style.overflow = 'hidden'; // 防止背景滚动
    }
  },

  /**
   * 关闭Modal
   * @param {string} modalId - Modal元素的ID
   */
  close(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) {
      modal.classList.add('hidden');
      modal.classList.remove('flex');
      document.body.style.overflow = ''; // 恢复滚动
    }
  },

  /**
   * 切换Modal状态
   * @param {string} modalId - Modal元素的ID
   */
  toggle(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) {
      if (modal.classList.contains('hidden')) {
        this.open(modalId);
      } else {
        this.close(modalId);
      }
    }
  },

  /**
   * 关闭所有Modal
   */
  closeAll() {
    const modals = document.querySelectorAll('[id$="-modal"], [id^="modal-"]');
    modals.forEach(modal => {
      modal.classList.add('hidden');
      modal.classList.remove('flex');
    });
    document.body.style.overflow = '';
  }
};

/**
 * API请求封装
 */
const ApiClient = {
  /**
   * 发送GET请求
   * @param {string} url - 请求URL
   * @param {Object} params - 查询参数
   * @returns {Promise<Object>} 响应数据
   */
  async get(url, params = {}) {
    const queryString = new URLSearchParams(params).toString();
    const fullUrl = queryString ? `${url}?${queryString}` : url;

    try {
      const response = await fetch(fullUrl, {
        method: 'GET',
        headers: {
          'Content-Type': 'application/json',
        },
      });

      return await this._handleResponse(response);
    } catch (error) {
      console.error('GET请求失败:', error);
      throw error;
    }
  },

  /**
   * 发送POST请求
   * @param {string} url - 请求URL
   * @param {Object} data - 请求数据
   * @returns {Promise<Object>} 响应数据
   */
  async post(url, data = {}) {
    try {
      const response = await fetch(url, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(data),
      });

      return await this._handleResponse(response);
    } catch (error) {
      console.error('POST请求失败:', error);
      throw error;
    }
  },

  /**
   * 发送DELETE请求
   * @param {string} url - 请求URL
   * @param {Object} data - 请求数据
   * @returns {Promise<Object>} 响应数据
   */
  async delete(url, data = {}) {
    try {
      const response = await fetch(url, {
        method: 'DELETE',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(data),
      });

      return await this._handleResponse(response);
    } catch (error) {
      console.error('DELETE请求失败:', error);
      throw error;
    }
  },

  /**
   * 处理响应
   * @private
   */
  async _handleResponse(response) {
    const data = await response.json();

    if (!response.ok) {
      throw new Error(data.error || data.message || '请求失败');
    }

    return data;
  }
};

/**
 * 防抖函数
 * @param {Function} func - 要执行的函数
 * @param {number} wait - 等待时间（毫秒）
 * @returns {Function} 防抖后的函数
 */
function debounce(func, wait = 300) {
  let timeout;
  return function executedFunction(...args) {
    const later = () => {
      clearTimeout(timeout);
      func(...args);
    };
    clearTimeout(timeout);
    timeout = setTimeout(later, wait);
  };
}

/**
 * 节流函数
 * @param {Function} func - 要执行的函数
 * @param {number} limit - 时间限制（毫秒）
 * @returns {Function} 节流后的函数
 */
function throttle(func, limit = 300) {
  let inThrottle;
  return function executedFunction(...args) {
    if (!inThrottle) {
      func(...args);
      inThrottle = true;
      setTimeout(() => (inThrottle = false), limit);
    }
  };
}

/**
 * 复制文本到剪贴板
 * @param {string} text - 要复制的文本
 * @returns {Promise<boolean>} 是否成功
 */
async function copyToClipboard(text) {
  try {
    await navigator.clipboard.writeText(text);
    showFlashMessage('success', '已复制到剪贴板');
    return true;
  } catch (error) {
    console.error('复制失败:', error);
    showFlashMessage('error', '复制失败');
    return false;
  }
}

/**
 * 确认对话框
 * @param {string} message - 确认消息
 * @param {string} title - 对话框标题
 * @returns {boolean} 用户是否确认
 */
function confirmAction(message, title = '确认操作') {
  return confirm(`${title}\n\n${message}`);
}

/**
 * 获取URL参数
 * @param {string} name - 参数名
 * @returns {string|null} 参数值
 */
function getUrlParam(name) {
  const params = new URLSearchParams(window.location.search);
  return params.get(name);
}

/**
 * 设置URL参数（不刷新页面）
 * @param {string} name - 参数名
 * @param {string} value - 参数值
 */
function setUrlParam(name, value) {
  const url = new URL(window.location);
  url.searchParams.set(name, value);
  window.history.pushState({}, '', url);
}

/**
 * 滚动到页面顶部
 * @param {boolean} smooth - 是否平滑滚动
 */
function scrollToTop(smooth = true) {
  window.scrollTo({
    top: 0,
    behavior: smooth ? 'smooth' : 'auto'
  });
}

/**
 * 等待指定时间
 * @param {number} ms - 毫秒数
 * @returns {Promise<void>}
 */
function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

// 导出到全局作用域
window.showFlashMessage = showFlashMessage;
window.formatDate = formatDate;
window.formatRelativeTime = formatRelativeTime;
window.escapeHtml = escapeHtml;
window.escapeJs = escapeJs;
window.formatFileSize = formatFileSize;
window.formatPercentage = formatPercentage;
window.ModalManager = ModalManager;
window.ApiClient = ApiClient;
window.debounce = debounce;
window.throttle = throttle;
window.copyToClipboard = copyToClipboard;
window.confirmAction = confirmAction;
window.getUrlParam = getUrlParam;
window.setUrlParam = setUrlParam;
window.scrollToTop = scrollToTop;
window.sleep = sleep;

// ESC键关闭所有Modal
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') {
    ModalManager.closeAll();
  }
});

console.log('✅ Utils.js 工具库已加载');
