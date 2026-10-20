(async()=>{
 const root=document.getElementById('account-login');
 try{
   if(await StoreAuth.currentUser()){location.replace('/');return;}
   let demo={};
   if(!new URLSearchParams(location.search).has('switch')){
     const response=await fetch('/api/v1/auth/demo-login');if(response.ok){const data=await response.json();if(data.enabled)demo={demo:true,username:data.username,password:data.password};}
   }
   const form=StoreAuth.createForm({...demo,onSuccess:()=>location.replace('/')});
   if(demo.demo){const hint=document.createElement('p');hint.className='auth-footnote';hint.textContent='演示账号已填好，点击登录进入南枝手作；也可使用自己的账号。';form.append(hint);}
   root.replaceChildren(form);
 }catch{
   root.replaceChildren(StoreAuth.createForm({onSuccess:()=>location.replace('/')}));
 }
})();
