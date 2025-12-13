function initialize_fc_lite() {

    // Cấu hình người dùng
    // Thiết lập cấu hình mặc định
    UserConfig = {
        private_api_url: UserConfig?.private_api_url || "", 
        page_turning_number: UserConfig?.page_turning_number || 20, // Mặc định 20 bài
        error_img: UserConfig?.error_img || "https://fastly.jsdelivr.net/gh/willow-god/Friend-Circle-Lite@latest/static/favicon.ico" // Avatar mặc định
    };

    const root = document.getElementById('friend-circle-lite-root');
    
    if (!root) return; // Đảm bảo phần tử gốc tồn tại

    // Xóa nội dung trước đó
    root.innerHTML = '';

    const randomArticleContainer = document.createElement('div');
    randomArticleContainer.id = 'random-article';
    root.appendChild(randomArticleContainer);

    const container = document.createElement('div');
    container.className = 'articles-container';
    container.id = 'articles-container';
    root.appendChild(container);
    
    const loadMoreBtn = document.createElement('button');
    loadMoreBtn.id = 'load-more-btn';
    loadMoreBtn.innerText = 'Thêm nữa';
    root.appendChild(loadMoreBtn);

    // Tạo container thông tin thống kê
    const statsContainer = document.createElement('div');
    statsContainer.id = 'stats-container';
    root.appendChild(statsContainer);

    let start = 0; // Ghi lại vị trí bắt đầu tải
    let allArticles = []; // Lưu trữ tất cả bài viết

    function loadMoreArticles() {
        const cacheKey = 'friend-circle-lite-cache';
        const cacheTimeKey = 'friend-circle-lite-cache-time';
        const cacheTime = localStorage.getItem(cacheTimeKey);
        const now = new Date().getTime();

        if (cacheTime && (now - cacheTime < 10 * 60 * 1000)) { // Thời gian cache nhỏ hơn 10 phút
            const cachedData = JSON.parse(localStorage.getItem(cacheKey));
            if (cachedData) {
                processArticles(cachedData);
                return;
            }
        }

        fetch(`${UserConfig.private_api_url}all.json`)
            .then(response => response.json())
            .then(data => {
                localStorage.setItem(cacheKey, JSON.stringify(data));
                localStorage.setItem(cacheTimeKey, now.toString());
                processArticles(data);
            })
            .finally(() => {
                loadMoreBtn.innerText = 'Thêm nữa'; // Khôi phục văn bản nút
            });
    }

    function processArticles(data) {
        allArticles = data.article_data;
        // Xử lý dữ liệu thống kê
        const stats = data.statistical_data;
        statsContainer.innerHTML = `
            <div>Powered by: <a href="https://www.facebook.com/thinhem.ic" target="_blank">Phung Duy Thinh</a><br></div>
            <div>Designed By: <a href="https://blog.inlove.eu.org" target="_blank">.Thinhem</a><br></div>
            <div>Subscribe:${stats.friends_num}   Active:${stats.active_num}   Total articles:${stats.article_num}<br></div>
            <div>Update time:${stats.last_updated_time}</div>
        `;

        displayRandomArticle(); // Hiển thị thẻ bạn bè ngẫu nhiên

        const articles = allArticles.slice(start, start + UserConfig.page_turning_number);

        articles.forEach(article => {
            const card = document.createElement('div');
            card.className = 'card';

            const title = document.createElement('div');
            title.className = 'card-title';
            title.innerText = article.title;
            card.appendChild(title);
            title.onclick = () => window.open(article.link, '_blank');

            const author = document.createElement('div');
            author.className = 'card-author';
            const authorImg = document.createElement('img');
            authorImg.className = 'no-lightbox';
            authorImg.src = article.avatar || UserConfig.error_img; // Sử dụng avatar mặc định
            authorImg.onerror = () => authorImg.src = UserConfig.error_img; // Sử dụng avatar mặc định khi tải avatar thất bại
            author.appendChild(authorImg);
            author.appendChild(document.createTextNode(article.author));
            card.appendChild(author);

            author.onclick = () => {
                showAuthorArticles(article.author, article.avatar, article.link);
            };

            const date = document.createElement('div');
            date.className = 'card-date';
            date.innerText = "🗓️" + article.created.substring(0, 10);
            card.appendChild(date);

            const bgImg = document.createElement('img');
            bgImg.className = 'card-bg no-lightbox';
            bgImg.src = article.avatar || UserConfig.error_img;
            bgImg.onerror = () => bgImg.src = UserConfig.error_img; // Sử dụng avatar mặc định khi tải avatar thất bại
            card.appendChild(bgImg);

            container.appendChild(card);
        });

        start += UserConfig.page_turning_number;

        if (start >= allArticles.length) {
            loadMoreBtn.style.display = 'none'; // Ẩn nút
        }
    }

    // Logic hiển thị bài viết ngẫu nhiên
    function displayRandomArticle() {
        const randomArticle = allArticles[Math.floor(Math.random() * allArticles.length)];
        randomArticleContainer.innerHTML = `
            <div class="random-container">
                <div class="random-container-title">Ngẫu nhiên</div>
                <div class="random-title">${randomArticle.title}</div>
                <div class="random-author">Tác giả: ${randomArticle.author}</div>
            </div>
            <div class="random-button-container">
                <a href="#" id="refresh-random-article">Làm mới</a>
                <button class="random-link-button" onclick="window.open('${randomArticle.link}', '_blank')">Ghé thăm</button>
            </div>
        `;

        // Thêm trình nghe sự kiện cho nút làm mới
        const refreshBtn = document.getElementById('refresh-random-article');
        refreshBtn.addEventListener('click', function (event) {
            event.preventDefault(); // Ngăn chặn hành vi chuyển hướng mặc định
            displayRandomArticle(); // Gọi logic hiển thị bài viết ngẫu nhiên
        });
    }

    function showAuthorArticles(author, avatar, link) {
        // Tạo cấu trúc modal nếu không tồn tại
        if (!document.getElementById('fclite-modal')) {
            const modal = document.createElement('div');
            modal.id = 'modal';
            modal.className = 'modal';
            modal.innerHTML = `
            <div class="modal-content">
                <img id="modal-author-avatar" src="" alt="">
                <a id="modal-author-name-link"></a>
                <div id="modal-articles-container"></div>
                <img id="modal-bg" src="" alt="">
            </div>
            `;
            root.appendChild(modal);
        }

        const modal = document.getElementById('modal');
        const modalArticlesContainer = document.getElementById('modal-articles-container');
        const modalAuthorAvatar = document.getElementById('modal-author-avatar');
        const modalAuthorNameLink = document.getElementById('modal-author-name-link');
        const modalBg = document.getElementById('modal-bg');

        modalArticlesContainer.innerHTML = ''; // Xóa nội dung trước đó
        modalAuthorAvatar.src = avatar  || UserConfig.error_img; // Sử dụng avatar mặc định
        modalAuthorAvatar.onerror = () => modalAuthorAvatar.src = UserConfig.error_img; // Sử dụng avatar mặc định khi tải avatar thất bại
        modalBg.src = avatar || UserConfig.error_img; // Sử dụng avatar mặc định
        modalBg.onerror = () => modalBg.src = UserConfig.error_img; // Sử dụng avatar mặc định khi tải avatar thất bại
        modalAuthorNameLink.innerText = author;
        modalAuthorNameLink.href = new URL(link).origin;

        const authorArticles = allArticles.filter(article => article.author === author);
        // Chỉ lấy năm bài đầu tiên, ngăn modal quá dài do quá nhiều bài viết, nếu không đủ năm thì lấy tất cả
        authorArticles.slice(0, 4).forEach(article => {
            const articleDiv = document.createElement('div');
            articleDiv.className = 'modal-article';

            const title = document.createElement('a');
            title.className = 'modal-article-title';
            title.innerText = article.title;
            title.href = article.link;
            title.target = '_blank';
            articleDiv.appendChild(title);

            const date = document.createElement('div');
            date.className = 'modal-article-date';
            date.innerText = "📅" + article.created.substring(0, 10);
            articleDiv.appendChild(date);

            modalArticlesContainer.appendChild(articleDiv);
        });

        // Đặt tên lớp để kích hoạt hiệu ứng hiển thị
        modal.style.display = 'block';
        setTimeout(() => {
            modal.classList.add('modal-open');
        }, 10); // Đảm bảo hiệu ứng hiển thị được kích hoạt
    }

    // Hàm ẩn modal
    function hideModal() {
        const modal = document.getElementById('modal');
        modal.classList.remove('modal-open');
        modal.addEventListener('transitionend', () => {
            modal.style.display = 'none';
            root.removeChild(modal);
        }, { once: true });
    }

    // Tải ban đầu
    loadMoreArticles();

    // Sự kiện nhấp nút tải thêm
    loadMoreBtn.addEventListener('click', loadMoreArticles);

    // Nhấp vào lớp phủ để đóng modal
    window.onclick = function(event) {
        const modal = document.getElementById('modal');
        if (event.target === modal) {
            hideModal();
        }
    };
};

function whenDOMReady() {
    initialize_fc_lite();
}

whenDOMReady();
document.addEventListener("pjax:complete", initialize_fc_lite);
