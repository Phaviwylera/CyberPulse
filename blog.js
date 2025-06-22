document.addEventListener('DOMContentLoaded', () => {
    const postContainer = document.getElementById('post-list-container');
    const searchInput = document.getElementById('search-input');
    let allPosts = []; // Variable to store all posts after fetching

    // Function to render a list of posts to the page
    function renderPosts(postsToRender) {
        if (!postsToRender || postsToRender.length === 0) {
            postContainer.innerHTML = '<p style="text-align: center;">No matching posts found.</p>';
            return;
        }

        let allPostsHTML = '';
        postsToRender.forEach(post => {
            let categoryTag = '';
            if (post.category) {
                const categorySlug = post.category.toLowerCase().replace(' ', '-');
                const categoryUrl = `category-${categorySlug}.html`;
                categoryTag = `<a href="${categoryUrl}" class="category-tag">${post.category}</a>`;
            }

            allPostsHTML += `
                <a href="${post.url}" class="post-link">
                    ${categoryTag}
                    <h2>${post.title}</h2>
                    <p>${post.summary}</p>
                </a>
            `;
        });
        postContainer.innerHTML = allPostsHTML;
    }

    // Fetch all posts once and store them
    fetch('blog-index.json')
        .then(response => response.json())
        .then(posts => {
            allPosts = posts;
            renderPosts(allPosts); // Render all posts initially
        })
        .catch(error => {
            console.error('Error fetching blog index:', error);
            postContainer.innerHTML = '<p>Error loading posts.</p>';
        });

    // **NEW** Event listener for the search input
    searchInput.addEventListener('input', (e) => {
        const searchTerm = e.target.value.toLowerCase();
        
        const filteredPosts = allPosts.filter(post => {
            const title = post.title.toLowerCase();
            const summary = post.summary.toLowerCase();
            return title.includes(searchTerm) || summary.includes(searchTerm);
        });

        renderPosts(filteredPosts);
    });
});